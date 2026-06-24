"""
This file contains various helpers and basic variables for the test suite.

Defining them here rather than in conftest.py avoids issues with circular imports
between test/conftest.py and test/backend/<backend>/conftest.py files.
"""

import faulthandler
import fcntl
import functools
import logging
import multiprocessing
import os
import signal
import subprocess
import sys
import tempfile
import time
import traceback
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


# Every qtile instance is launched in a "forkserver" child rather than by
# fork()ing the pytest process directly. The forkserver is a fresh, single
# threaded interpreter (exec()ed, not forked from us), so the qtile children it
# forks never inherit the pango/glycin worker threads that in-process rendering
# and image-decoding tests leave lying around in the pytest process. That kills
# both the "multi-threaded, use of fork()" DeprecationWarning and the font-map
# deadlocks (g_cond_wait) that those inherited threads used to cause.
mp_context = multiprocessing.get_context("forkserver")

# Imports that are heavy but thread-free at import time. Preloading them once in
# the forkserver means every qtile child inherits them warm. test.helpers may
# not be importable from the forkserver's default sys.path; an ImportError there
# is silently ignored by the forkserver and the child imports it on demand.
_FORKSERVER_PRELOAD = [
    "libqtile.core.manager",
    "libqtile.pangocffi",
    "libqtile.images",
    "test.helpers",
]


def _forkserver_noop():
    pass


def prime_forkserver():
    """Start the forkserver now, while the pytest process is still clean.

    Called once at session start (see test/conftest.py). The forkserver is a
    fresh exec()ed interpreter regardless of when it starts, so this is mostly
    about pinning the preload list and paying the startup/import cost up front.
    """
    multiprocessing.set_forkserver_preload(_FORKSERVER_PRELOAD)
    proc = mp_context.Process(target=_forkserver_noop)
    proc.start()
    proc.join()


class _ConnLogHandler(logging.Handler):
    """Ship formatted log records to the parent over a multiprocessing pipe.

    A forkserver child cannot be handed a raw os.pipe() fd (only Connection
    objects survive the pickling), so the child's logs go back through a
    Connection instead of the StreamHandler-over-fd the fork harness used.
    """

    def __init__(self, conn):
        super().__init__()
        self.conn = conn

    def emit(self, record):
        try:
            self.conn.send(self.format(record))
        except Exception:
            self.handleError(record)


def _run_qtile(
    backend_core,
    backend_env,
    backend_args,
    parent_env,
    config_class,
    sockfile,
    log_level,
    no_spawn,
    state,
    error_conn,
    log_conn,
):
    """Entry point for the forkserver child that runs a qtile instance.

    Everything here must be reconstructable from picklable arguments: the
    backend Core *class* plus its env/args (not the unpicklable Backend instance,
    which back-references the TestManager), a module-level config class, and the
    Connection write ends for startup errors and logging.
    """
    try:
        # A hung child during startup should still dump stacks on SIGUSR2, the
        # way the fork harness's inherited faulthandler used to.
        faulthandler.enable(all_threads=True)
        faulthandler.register(signal.SIGUSR2, all_threads=True)

        # The forkserver was exec()ed early, so it carries a stale environment.
        # Restore the pytest parent's current environment so the child sees
        # anything a test set up before start() (e.g. DBUS_SESSION_BUS_ADDRESS),
        # matching what fork() used to give us for free.
        os.environ.update(parent_env)
        os.environ.pop("DISPLAY", None)
        os.environ.pop("WAYLAND_DISPLAY", None)
        init_log(log_level)
        # Initialise fontconfig before starting qtile to prevent races
        pangocffi.init_fontconfig()

        # Recreate what Backend.create() does, without the Backend instance:
        # update the environment (wayland's Core reads it at construction).
        os.environ.update(backend_env)

        handler = _ConnLogHandler(log_conn)
        handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        logger.addHandler(handler)

        from libqtile.core.lifecycle import lifecycle

        # Build the config *before* constructing the Core. Config builders run
        # here (in the child) and may subscribe hooks; the wayland Core fires
        # screen_change from qw_server_start() during __init__, so the
        # subscriber must already be registered. With fork() the parent
        # subscribed before forking and the child inherited it; forkserver has
        # no such inheritance, so we order the work explicitly.
        config = config_class()
        kore = backend_core(*backend_args)

        Qtile(
            kore,
            config,
            socket_path=sockfile,
            no_spawn=no_spawn,
            state=state,
        ).loop()
        lifecycle._atexit()
    except Exception:
        try:
            error_conn.send(traceback.format_exc())
        except Exception:
            pass
    finally:
        error_conn.close()
        log_conn.close()


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
        self._log_recv = None

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
        if self._log_recv is not None:
            self._log_recv.close()

    def get_log_buffer(self):
        """Returns any logs that have been written to qtile's log buffer up to this point."""
        out = []
        while self._log_recv.poll():
            out.append(self._log_recv.recv())
        return "".join(line + "\n" for line in out)

    def start(self, config_class, no_spawn=False, state=None):
        # Two child->parent Connections: one for the startup traceback, one for
        # the qtile log stream. mp_context.Pipe(duplex=False) is backed by an
        # os.pipe() (not a socketpair), so we can grow the kernel buffer; a
        # handful of tests drain logs via get_log_buffer() and the rest must not
        # block qtile in a full-pipe write().
        error_recv, error_send = mp_context.Pipe(duplex=False)
        log_recv, log_send = mp_context.Pipe(duplex=False)
        try:
            fcntl.fcntl(log_recv.fileno(), fcntl.F_SETPIPE_SZ, LOG_PIPE_BUFFER_SIZE)
        except (OSError, AttributeError):
            pass

        self.proc = mp_context.Process(
            target=_run_qtile,
            args=(
                self.backend.core,
                self.backend.env,
                tuple(self.backend.args),
                dict(os.environ),
                config_class,
                self.sockfile,
                self.log_level,
                no_spawn,
                state,
                error_send,
                log_send,
            ),
        )
        self.proc.start()
        # The write ends now live in the child; drop the parent's copies so the
        # pipes report EOF/closed correctly once the child exits.
        error_send.close()
        log_send.close()
        self._log_recv = log_recv

        # First, wait for socket to appear
        try:
            if can_connect_qtile(self.sockfile, ok=lambda: not error_recv.poll()):
                ipc_client = ipc.Client(self.sockfile)
                ipc_command = command.interface.IPCCommandInterface(ipc_client)
                self.c = command.client.InteractiveCommandClient(ipc_command)
                self.backend.configure(self)
                return
            if error_recv.poll(0.1):
                error = error_recv.recv()
                raise AssertionError(f"Error launching qtile, traceback:\n{error}")
            raise AssertionError("Error launching qtile")
        finally:
            error_recv.close()

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
        if self.proc is None or self.proc._popen is None:
            # self.proc._popen is None when Process.start() raised (e.g. the
            # config failed to pickle); there is nothing to terminate, and
            # calling .terminate() would just mask the real error.
            print("qtile is not alive", file=sys.stderr)
            self.proc = None
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
            while failed is None or not failed():
                if len(client.windows()) > start:
                    return True
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
