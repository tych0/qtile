"""
This file contains various helpers and basic variables for the test suite.

Defining them here rather than in conftest.py avoids issues with circular imports
between test/conftest.py and test/backend/<backend>/conftest.py files.
"""

import contextlib
import faulthandler
import functools
import logging
import multiprocessing
import os
import select
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from abc import ABCMeta, abstractmethod
from pathlib import Path

from libqtile import command, config, ipc, layout, pangocffi
from libqtile.confreader import Config
from libqtile.core.manager import Qtile
from libqtile.lazy import lazy
from libqtile.log_utils import init_log, logger
from libqtile.resources import default_config

# the sizes for outputs
WIDTH = 800
HEIGHT = 600
SECOND_WIDTH = 640
SECOND_HEIGHT = 480

LOG_PIPE_BUFFER_SIZE = 128 * 1024

max_sleep = 5.0
sleep_time = 0.1

# Everything is slower when several pytest-xdist workers share the machine,
# so give condition polling more headroom. This only slows down failures.
if os.environ.get("PYTEST_XDIST_WORKER"):
    max_sleep *= 4


# Worker threads that C libraries (pango, GLib, ...) spawn in the pytest
# process can deadlock a fork()ed child, so any fork of a multi-threaded test
# process must be one of the sites we have deliberately made fork-safe,
# marked with expected_fork(). CPython's corresponding DeprecationWarning
# cannot be promoted to an error (os.fork() swallows the exception, silencing
# the warning instead), and exceptions from at-fork hooks are ignored, so the
# guard records violations here and a conftest autouse fixture fails the
# offending test.
fork_violations = []
_expected_forks = 0


@contextlib.contextmanager
def expected_fork():
    """Mark a fork of the test process as known to be fork-safe.

    Also silences multiprocessing's "multi-threaded process" warning for the
    fork, since the whole point of the marker is that we have made the child
    safe against the inherited threads.
    """
    global _expected_forks
    _expected_forks += 1
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "This process", DeprecationWarning)
            yield
    finally:
        _expected_forks -= 1


def _fork_guard():
    if _expected_forks:
        return
    stack = traceback.extract_stack()
    if any(f.filename.endswith("forkedfunc.py") for f in stack):
        # pytest-forked's isolation forks: the child runs a single test and
        # exits, precisely to keep thread-spawning work away from this
        # process, so it never waits on an inherited thread
        return
    try:
        native_threads = sum(1 for _ in Path("/proc/self/task").iterdir())
    except OSError:
        return
    if native_threads > 1:
        fork_violations.append(
            f"fork() of the test process while it has {native_threads} threads, at:\n"
            + "".join(traceback.format_stack())
        )


os.register_at_fork(before=_fork_guard)


class Retry:
    def __init__(
        self,
        ignore_exceptions=(),
        dt=sleep_time,
        tmax=max_sleep,
        return_on_fail=False,
    ):
        self.ignore_exceptions = ignore_exceptions
        self.dt = dt
        self.tmax = tmax
        self.return_on_fail = return_on_fail
        self.last_failure = None

    def __call__(self, fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            tmax = time.time() + self.tmax
            dt = self.dt
            ignore_exceptions = self.ignore_exceptions

            while time.time() <= tmax:
                try:
                    return fn(*args, **kwargs)
                except ignore_exceptions as e:
                    self.last_failure = e
                except AssertionError:
                    break
                time.sleep(dt)
                dt *= 1.5
            if self.return_on_fail:
                return False
            else:
                raise self.last_failure

        return wrapper


class BareConfig(Config):
    auto_fullscreen = True
    groups = [config.Group("a"), config.Group("b"), config.Group("c"), config.Group("d")]
    layouts = [layout.stack.Stack(num_stacks=1), layout.stack.Stack(num_stacks=2)]
    floating_layout = default_config.floating_layout
    keys = [
        config.Key(
            ["control"],
            "k",
            lazy.layout.up(),
        ),
        config.Key(
            ["control"],
            "j",
            lazy.layout.down(),
        ),
    ]
    mouse = []
    screens = [config.Screen()]
    follow_mouse_focus = False
    reconfigure_screens = False


class Backend(metaclass=ABCMeta):
    """A base class to help set up backends passed to TestManager"""

    def __init__(self, env, args=()):
        self.env = env
        self.args = args

    def create(self):
        """This is used to instantiate the Core"""
        return self.core(*self.args)

    def configure(self, manager):
        """This is used to do any post-startup configuration with the manager"""

    @abstractmethod
    def fake_click(self, x, y):
        """Click at the specified coordinates"""

    @abstractmethod
    def get_all_windows(self):
        """Get a list of all windows in ascending order of Z position"""


@Retry(ignore_exceptions=(ipc.IPCError,), return_on_fail=True)
def can_connect_qtile(socket_path, *, ok=None):
    if ok is not None and not ok():
        raise AssertionError()

    ipc_client = ipc.Client(socket_path)
    ipc_command = command.interface.IPCCommandInterface(ipc_client)
    client = command.client.InteractiveCommandClient(ipc_command)
    val = client.status()
    if val == "OK":
        return True
    return False


class TestManager:
    """Spawn a Qtile instance

    Setup a Qtile server instance on the given display, with the given socket
    and log files.  The Qtile server must be started, and then stopped when it
    is done.  Windows can be spawned for the Qtile instance to interact with
    with various `.test_*` methods.
    """

    def __init__(self, backend, debug_log):
        self.backend = backend
        self.log_level = logging.DEBUG if debug_log else logging.INFO
        self.backend.manager = self

        self.proc = None
        self.c = None
        self.testwindows = []
        self.logspipe = None

    def timeout_handler(self, signum, frame):
        os.kill(self.proc.pid, signal.SIGUSR2)
        subprocess.run(["ps", "awfux"], stdout=sys.stderr)
        old = self._old_sigalrm_handler
        if callable(old):
            old(signum, frame)

    def __enter__(self):
        """Set up resources"""
        faulthandler.enable(all_threads=True)
        faulthandler.register(signal.SIGUSR2, all_threads=True)
        self._old_sigalrm_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self.timeout_handler)
        faulthandler.register(signal.SIGALRM, all_threads=True, chain=True)
        self._sockfile = tempfile.NamedTemporaryFile()
        self.sockfile = self._sockfile.name
        return self

    def __exit__(self, _exc_type, _exc_value, _exc_tb):
        """Clean up resources"""
        self.terminate()
        self._sockfile.close()
        if self.logspipe is not None:
            os.close(self.logspipe)

    def get_log_buffer(self):
        """Returns any logs that have been written to qtile's log buffer up to this point."""
        # default pipe size on linux is 64k. we probably won't write
        # 64k of logs, but in the event that we do, qtile will hang in
        # write(). but thanks to e1d2dab16903 ("switch semantics of sigusr2
        # to stack dumping") hopefully we will see it's hung in a log write and
        # look at this. if we do write 64k of logs, we can do some F_SETPIPE_SZ
        # fiddling with the buffer size to grow it to whatever github allows.
        return os.read(self.logspipe, 64 * 1024).decode("utf-8")

    def _drain_logs(self):
        if self.logspipe is None:
            return ""
        chunks = []
        while True:
            readable, _, _ = select.select([self.logspipe], [], [], 0)
            if not readable:
                break
            try:
                data = os.read(self.logspipe, 64 * 1024)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks).decode("utf-8", "replace")

    def _dump_logs(self, header):
        logs = self._drain_logs()
        if logs:
            print(f"{header}\n{logs}", file=sys.stderr)

    def start(self, config_class, no_spawn=False, state=None):
        multiprocessing.set_start_method("fork", force=True)
        readlogs, writelogs = os.pipe()
        rpipe, wpipe = multiprocessing.Pipe()

        def run_qtile():
            try:
                rpipe.close()
                os.close(readlogs)
                os.environ.pop("DISPLAY", None)
                os.environ.pop("WAYLAND_DISPLAY", None)
                # Make every IPC command a synchronization barrier, so that
                # when a client call returns, qtile has processed all of the
                # events that the command generated (see IPCCommandServer).
                # This is an environment variable so it survives restart().
                os.environ["QTILE_SYNC_COMMANDS"] = "1"
                init_log(self.log_level)

                formatter = logging.Formatter("%(levelname)s - %(message)s")
                handler = logging.StreamHandler(os.fdopen(writelogs, "w"))
                handler.setFormatter(formatter)
                logger.addHandler(handler)

                # Initialise fontconfig before starting qtile to prevent races
                pangocffi.init_fontconfig()
                # We've just fork()ed from the pytest process. If that process
                # rendered any text (lots of the unit tests do), Pango spun up a
                # "[pango] fontcon" helper thread to load fonts, and fork() did
                # not copy it. Loading an as-yet-uncached font here would then
                # block forever in g_cond_wait waiting on that missing thread --
                # qtile would hang right after the compositor starts. Drop the
                # inherited font map so this process builds its own.
                pangocffi.reset_font_map()
                kore = self.backend.create()
                os.environ.update(self.backend.env)
                from libqtile.core.lifecycle import lifecycle

                Qtile(
                    kore,
                    config_class(),
                    socket_path=self.sockfile,
                    no_spawn=no_spawn,
                    state=state,
                ).loop()
                lifecycle._atexit()
            except Exception:
                wpipe.send(traceback.format_exc())
            finally:
                wpipe.close()

        self.proc = multiprocessing.Process(target=run_qtile)
        # This fork is engineered to be safe despite threads in the pytest
        # process: run_qtile() resets the inherited pango state, in-process
        # image decoding is isolated into pytest-forked subprocesses, and the
        # remaining threads (e.g. pytest-xdist's execnet IO threads,
        # pytest-httpbin's server) are ones qtile children have always
        # coexisted with. A child that does deadlock is still caught:
        # can_connect_qtile() times out and the child's logs are dumped to
        # stderr.
        with expected_fork():
            self.proc.start()
        wpipe.close()
        os.close(writelogs)
        self.logspipe = readlogs

        # First, wait for socket to appear
        try:
            if can_connect_qtile(self.sockfile, ok=lambda: not rpipe.poll()):
                ipc_client = ipc.Client(self.sockfile)
                ipc_command = command.interface.IPCCommandInterface(ipc_client)
                self.c = command.client.InteractiveCommandClient(ipc_command)
                self.backend.configure(self)
                return
            self._dump_logs("qtile failed to start; captured std* output:")
            if rpipe.poll(0.1):
                error = rpipe.recv()
                raise AssertionError(f"Error launching qtile, traceback:\n{error}")
            raise AssertionError("Error launching qtile")
        finally:
            rpipe.close()

    def create_manager(self, config_class):
        """Create a Qtile manager instance in this thread

        This should only be used when it is known that the manager will throw
        an error and the returned manager should not be started, otherwise this
        will likely block the thread.
        """
        init_log(self.log_level)
        kore = self.backend.create()
        config = config_class()
        for attr in dir(default_config):
            if not hasattr(config, attr):
                setattr(config, attr, getattr(default_config, attr))

        return Qtile(kore, config, socket_path=self.sockfile)

    def terminate(self):
        if self.proc is None:
            print("qtile is not alive", file=sys.stderr)
        else:
            # try to send SIGTERM and wait up to 10 sec to quit
            self.proc.terminate()
            self.proc.join(10)

            if self.proc.is_alive():
                # uh oh, we're hung somewhere. give it another second to print
                # some stack traces
                os.kill(self.proc.pid, signal.SIGUSR2)
                self.proc.join(1)
                print("Killing qtile forcefully", file=sys.stderr)
                # desperate times... this probably messes with multiprocessing...
                try:
                    os.kill(self.proc.pid, signal.SIGKILL)
                    self.proc.join()
                except OSError:
                    # The process may have died due to some other error
                    pass

            if self.proc.exitcode:
                print(f"qtile exited with exitcode: {self.proc.exitcode:d}", file=sys.stderr)
                self._dump_logs("qtile log output before exit:")

            self.proc = None

        for proc in self.testwindows[:]:
            proc.terminate()
            proc.wait()

            self.testwindows.remove(proc)

    def create_window(self, create, failed=None):
        """
        Uses the function `create` to create a window.

        Waits until qtile actually maps the window and then returns.
        """
        client = self.c
        start = len(client.windows())
        create()

        @Retry(ignore_exceptions=(RuntimeError,))
        def success():
            if len(client.windows()) > start:
                return True
            if failed is not None and failed():
                raise RuntimeError("client process died without creating a window")
            raise RuntimeError("window has not appeared yet")

        return success()

    def _spawn_window(self, *args):
        """Starts a program which opens a window

        Spawns a new subprocess for a command that opens a window, given by the
        arguments to this method.  Spawns the new process and checks that qtile
        maps the new window.
        """
        if not args:
            raise AssertionError("Trying to run nothing! (missing arguments)")

        proc = None

        def spawn():
            nonlocal proc
            # Ensure the client only uses the test display
            env = os.environ.copy()
            env.pop("DISPLAY", None)
            env.pop("WAYLAND_DISPLAY", None)
            env.update(self.backend.env)
            proc = subprocess.Popen(args, env=env)

        def failed():
            if proc.poll() is not None:
                return True
            return False

        self.create_window(spawn, failed=failed)
        self.testwindows.append(proc)
        return proc

    def kill_window(self, proc):
        """Kill a window and check that qtile unmaps it

        Kills a window created by calling one of the `self.test*` methods,
        ensuring that qtile removes it from the `windows` attribute.
        """
        assert proc in self.testwindows, "Given process is not a spawned window"
        start = len(self.c.windows())
        proc.terminate()
        proc.wait()
        self.testwindows.remove(proc)

        @Retry(ignore_exceptions=(ValueError,))
        def success():
            if len(self.c.windows()) < start:
                return True
            raise ValueError("window is still in client list!")

        if not success():
            raise AssertionError("Window could not be killed...")

    def test_window(
        self,
        name,
        floating=False,
        wm_type="normal",
        new_title=None,
        urgent=False,
        export_sni=False,
    ):
        """
        Create a simple window in X or Wayland. If `floating` is True then the wmclass
        is set to "dialog", which triggers auto-floating based on `default_float_rules`.
        `wm_type` can be changed from "normal" to "notification", which creates a window
        that not only floats but does not grab focus.

        Setting `export_sni` to True will publish a simplified StatusNotifierItem interface
        on DBus.

        Windows created with this method must have their process killed explicitly, no
        matter what type they are.
        """
        os.environ.pop("GDK_BACKEND", None)
        python = sys.executable
        path = Path(__file__).parent / "scripts" / "window.py"
        wmclass = "dialog" if floating else "TestWindow"
        args = [python, path, "--name", wmclass, name, wm_type]
        if new_title:
            args += ["--new-title", new_title]
        if urgent:
            args.append("--urgent")
            # Set GDK_BACKEND to x11, since in wayland, the window requieres
            # of an input event which cannot be passed to the headless session
            os.environ["GDK_BACKEND"] = "x11"
        if export_sni:
            args.append("--export-sni-interface")
        return self._spawn_window(*args)

    def test_notification(self, name="notification"):
        return self.test_window(name, wm_type="notification")

    def groupconsistency(self):
        groups = self.c.get_groups()
        screens = self.c.get_screens()
        seen = set()
        for g in groups.values():
            scrn = g["screen"]
            if scrn is not None:
                if scrn in seen:
                    raise AssertionError("Screen referenced from more than one group.")
                seen.add(scrn)
                assert screens[scrn]["group"] == g["name"]
        assert len(seen) == len(screens), "Not all screens had an attached group."


@Retry(ignore_exceptions=(AssertionError,))
def assert_window_died(client, window_info):
    client.sync()
    wid = window_info["id"]
    assert wid not in set([x["id"] for x in client.windows()]), f"window {wid} still here"


def window_by_name(client, name):
    return client.window[{w["name"]: w["id"] for w in client.windows()}[name]]
