import contextlib
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


@contextlib.contextmanager
def xvfb():
    with xcffib.testing.XvfbTest():
        display = os.environ["DISPLAY"]
        if not can_connect_x11(display):
            raise OSError("Xvfb did not come up")

        yield


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
        raise AssertionError(f"Unable to connect to running {args[0]}")
    else:
        raise AssertionError(
            f"Unable to start {args[0]}, quit with return code {proc.returncode}"
        )


def stop_x11(proc, display, display_file):
    # Kill xephyr only if it is running
    if proc is not None:
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    # clean up the lock file for the display we allocated
    try:
        display_file.close()
        os.remove(xcffib.testing.lock_path(int(display[1:])))
    except OSError:
        pass


@contextlib.contextmanager
def x11_environment(outputs, **kwargs):
    with xvfb() as x:
        yield x


@pytest.fixture(scope="function")
def xmanager(request, xvfb):
    """
    This replicates the `manager` fixture except that the x11 backend is hard-coded. We
    cannot simply parametrize the `backend_name` fixture module-wide because it gets
    parametrized by `pytest_generate_tests` in test/conftest.py and only one of these
    parametrize calls can be used.
    """
    config = getattr(request, "param", BareConfig)
    backend = XBackend(os.environ)

    with TestManager(backend, request.config.getoption("--debuglog")) as manager:
        manager.display = os.environ["DISPLAY"]
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
    backend = XBackend(os.environ)

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

    def __init__(self, env):
        self.env = env
        self.core = Core
        self.manager = None

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
