import contextlib
import fcntl
import os
import subprocess

import pytest
import xcffib
import xcffib.testing
import xcffib.xproto
import xcffib.xtest

from libqtile.backend.x11.core import Core
from libqtile.backend.x11.xcbq import Connection
from test.helpers import (
    HEIGHT,
    SECOND_HEIGHT,
    SECOND_WIDTH,
    WIDTH,
    Backend,
    BareConfig,
    Retry,
    TestManager,
)


@Retry(ignore_exceptions=(xcffib.ConnectionException,), return_on_fail=True)
def can_connect_x11(disp=":0", *, ok=None):
    if ok is not None and not ok():
        raise AssertionError()

    conn = xcffib.connect(display=disp)
    conn.disconnect()
    return True


def socket_path(display: int) -> str:
    return f"/tmp/.X11-unix/X{display}"


@contextlib.contextmanager
def display_allocation_lock():
    """Serialize X display allocation across concurrent test sessions.

    xcffib.testing.find_display()'s flock-based protocol is not safe against
    concurrent allocators (e.g. pytest-xdist workers): the starting X server
    replaces the (empty) lock file that find_display() created, after which a
    concurrent find_display() can successfully flock the new inode and hand
    out the same display number again. Instead, we serialize the whole
    "pick a display and start a server on it" sequence with one global lock;
    once the server is up, its own lock file and socket mark the display as
    busy for everybody else.

    The lock file is per-uid so that we never fail on another user's lock
    file permissions; concurrent sessions of *different* users are instead
    handled by start_x11_server() retrying on the next display when a server
    loses the race for one.
    """
    with open(f"/tmp/.qtile-test-displays.{os.getuid()}.lock", "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def display_is_free(display: int) -> bool:
    """Check whether an X server could be started on this display number.

    Only meaningful while holding display_allocation_lock(). If a previous
    test session was killed before it could clean up, we may find a stale
    lock file and/or socket; reclaim the display in that case, since a new
    server refuses to start while a stale socket exists.
    """
    lock = xcffib.testing.lock_path(display)
    if not os.path.exists(lock) and not os.path.exists(socket_path(display)):
        return True

    # There is some leftover state; check whether an X server actually owns
    # this display before touching it.
    try:
        with open(lock) as f:
            os.kill(int(f.read().strip()), 0)
        return False  # the lock file's owner is alive
    except (OSError, ValueError):
        pass
    try:
        conn = xcffib.connect(display=f":{display}")
        conn.disconnect()
        return False  # something is listening anyway
    except xcffib.ConnectionException:
        pass

    # The display is stale; clean it up so a new server can bind it.
    with contextlib.suppress(OSError):
        os.remove(lock)
    with contextlib.suppress(OSError):
        os.remove(socket_path(display))
    return True


def start_x11_server(make_args, tries=10):
    """Allocate a free display and start an X server on it.

    make_args is a callable taking the display string (e.g. ":10") and
    returning the server's argv. The search for a free display and the
    server's claiming of it (its lock file and socket exist once it is
    connectable) happen under a global lock so that concurrent test sessions
    cannot race for the same display number.

    Returns (proc, display).
    """
    with display_allocation_lock():
        display = 10
        last_error = None
        for _ in range(tries):
            while not display_is_free(display):
                display += 1
            display_str = f":{display}"
            try:
                proc = start_x11_and_poll_connection(make_args(display_str), display_str)
                return proc, display_str
            except AssertionError as e:
                # The server failed to come up; possibly something we cannot
                # see owns this display anyway. Try the next one.
                last_error = e
                display += 1
        raise AssertionError(f"Could not start an X server after {tries} tries: {last_error}")


@contextlib.contextmanager
def xvfb():
    proc = None
    display = None
    old_display = os.environ.get("DISPLAY")
    try:
        proc, display = start_x11_server(
            lambda d: ["Xvfb", d, "-screen", "0", f"{WIDTH}x{HEIGHT}x16"]
        )
        # Anything else we start (in particular Xephyr) finds this Xvfb via
        # DISPLAY.
        os.environ["DISPLAY"] = display
        yield
    finally:
        if old_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = old_display
        if display is not None:
            stop_x11(proc, display)


@pytest.fixture(scope="session")
def display():  # noqa: F841
    with xvfb():
        yield os.environ["DISPLAY"]


def start_x11_and_poll_connection(args, display):
    proc = subprocess.Popen(args)

    if can_connect_x11(display, ok=lambda: proc.poll() is None):
        return proc

    # we weren't able to get a display up
    if proc.poll() is None:
        proc.kill()
        proc.wait()
        raise AssertionError(f"Unable to connect to running {args[0]}")
    else:
        raise AssertionError(
            f"Unable to start {args[0]}, quit with return code {proc.returncode}"
        )


def stop_x11(proc, display):
    if proc is None:
        return

    with display_allocation_lock():
        # Kill the server only if it is running
        if proc.poll() is None:
            proc.kill()
        proc.wait()

        # A killed X server cannot unlink its own lock file and socket, and a
        # stale socket stops the next server on this display number from
        # starting, so clean them up. display_is_free() removes exactly the
        # leftovers of a dead server, which also keeps us from deleting the
        # files of a server that legitimately reclaimed the display (possible
        # if ours crashed some time ago).
        display_is_free(int(display[1:]))


class Xephyr:
    """Spawn Xephyr instance

    Set-up a Xephyr instance with the given parameters.  The Xephyr instance
    must be started, and then stopped.
    """

    def __init__(self, outputs, xoffset=None, xtrace=False):
        self.outputs = outputs
        if xoffset is None:
            self.xoffset = WIDTH
        else:
            self.xoffset = xoffset

        self.proc = None  # Handle to Xephyr instance, subprocess.Popen object
        self.display = None

        self.xtrace = xtrace
        self.xtrace_proc = None
        self.xtrace_display = None
        self.xephyr_display = None

    def __enter__(self):
        try:
            self.start_xephyr()
        except:  # noqa: E722
            self.stop_xephyr()
            raise

        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self.stop_xephyr()

    def start_xephyr(self):
        """Start Xephyr instance

        Starts the Xephyr instance and sets the `self.display` to the display
        which is used to setup the instance.
        """

        def make_args(display):
            args = [
                "Xephyr",
                "-name",
                "qtile_test",
                display,
                "-ac",
                "-screen",
                f"{WIDTH}x{HEIGHT}",
            ]
            if self.outputs == 2:
                args.extend(
                    [
                        "-origin",
                        f"{self.xoffset},0",
                        "-screen",
                        f"{SECOND_WIDTH}x{SECOND_HEIGHT}",
                    ]
                )
                args.extend(["+xinerama"])
                args.extend(["-extension", "RANDR"])
            return args

        self.proc, self.display = start_x11_server(make_args)
        self.xephyr_display = self.display

        if self.xtrace:
            # because we run Xephyr without auth and xtrace requires auth, we
            # need to add some x11 auth here for the Xephyr display our xtrace
            # will fail:
            subprocess.check_call(["xauth", "generate", self.xephyr_display])

            def make_xtrace_args(display):
                return [
                    "xtrace",
                    "--timestamps",
                    "-k",
                    "-d",
                    self.xephyr_display,
                    "-D",
                    display,
                ]

            self.xtrace_proc, self.xtrace_display = start_x11_server(make_xtrace_args)
            self.display = self.xtrace_display

    def stop_xephyr(self):
        if self.xephyr_display is not None:
            stop_x11(self.proc, self.xephyr_display)
        if self.xtrace and self.xtrace_display is not None:
            stop_x11(self.xtrace_proc, self.xtrace_display)


@contextlib.contextmanager
def x11_environment(outputs, **kwargs):
    """This backend needs a Xephyr instance running"""
    with xvfb():
        with Xephyr(outputs, **kwargs) as x:
            yield x


@pytest.fixture(scope="function")
def xmanager(request, xephyr):
    """
    This replicates the `manager` fixture except that the x11 backend is hard-coded. We
    cannot simply parametrize the `backend_name` fixture module-wide because it gets
    parametrized by `pytest_generate_tests` in test/conftest.py and only one of these
    parametrize calls can be used.
    """
    config = getattr(request, "param", BareConfig)
    backend = XBackend({"DISPLAY": xephyr.display}, args=[xephyr.display])

    with TestManager(backend, request.config.getoption("--debuglog")) as manager:
        manager.display = xephyr.display
        manager.start(config)
        yield manager


@pytest.fixture(scope="function")
def xmanager_nospawn(request, xephyr):
    """
    This replicates the `manager` fixture except that the x11 backend is hard-coded. We
    cannot simply parametrize the `backend_name` fixture module-wide because it gets
    parametrized by `pytest_generate_tests` in test/conftest.py and only one of these
    parametrize calls can be used.
    """
    backend = XBackend({"DISPLAY": xephyr.display}, args=[xephyr.display])

    with TestManager(backend, request.config.getoption("--debuglog")) as manager:
        manager.display = xephyr.display
        yield manager


@pytest.fixture(scope="function")
def conn(xmanager):
    conn = Connection(xmanager.display)
    yield conn
    conn.finalize()


class XBackend(Backend):
    name = "x11"

    def __init__(self, env, args=()):
        self.env = env
        self.args = args
        self.core = Core
        self.manager = None

    def fake_motion(self, x, y):
        """Move pointer to the specified coordinates"""
        conn = Connection(self.env["DISPLAY"])
        root = conn.default_screen.root.wid
        xtest = conn.conn(xcffib.xtest.key)
        xtest.FakeInput(6, 0, xcffib.xproto.Time.CurrentTime, root, x, y, 0)
        conn.conn.flush()
        self.manager.c.sync()
        conn.finalize()

    def fake_click(self, x, y):
        """Click at the specified coordinates"""
        conn = Connection(self.env["DISPLAY"])
        root = conn.default_screen.root.wid
        xtest = conn.conn(xcffib.xtest.key)
        xtest.FakeInput(6, 0, xcffib.xproto.Time.CurrentTime, root, x, y, 0)
        xtest.FakeInput(4, 1, xcffib.xproto.Time.CurrentTime, root, 0, 0, 0)
        xtest.FakeInput(5, 1, xcffib.xproto.Time.CurrentTime, root, 0, 0, 0)
        conn.conn.flush()
        self.manager.c.sync()
        conn.finalize()

    def get_all_windows(self):
        """Get a list of all windows in ascending order of Z position"""
        conn = Connection(self.env["DISPLAY"])
        root = conn.default_screen.root.wid
        q = conn.conn.core.QueryTree(root).reply()
        wins = list(q.children)
        conn.finalize()
        return wins
