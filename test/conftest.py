import os

import pytest

import libqtile
from libqtile import pangocffi
from libqtile.backend.base import drawer
from test.helpers import BareConfig, TestManager

_MAIN_PID = os.getpid()

try:
    import marshal

    import py as _py
    import pytest_forked as _pytest_forked
    from _pytest import runner as _pytest_runner
    from _pytest.runner import runtestprotocol as _runtestprotocol
except ImportError:
    _pytest_forked = None

if _pytest_forked is not None:

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(item, nextitem):
        """Run forked-marked tests without tearing down shared state in the child.

        pytest-forked runs the whole test protocol in the child with
        nextitem=None, which pytest takes to mean "this was the last test":
        the child then finalizes every live fixture, including session-scoped
        ones it shares (as fork()ed copies) with the parent. That is both
        deadlocky and destructive: shutting down pytest-httpbin's server
        waits forever on a server thread that does not exist in the child
        (the CI hangs bisected to the first forked test after an httpbin
        test), and the teardown after that would kill() the parent's shared
        session X servers. Run the protocol with the item itself as nextitem
        instead, which keeps all shared-scope fixtures alive; anything the
        test itself created is discarded with the child's exit.
        """
        if not (item.config.getvalue("forked") or item.get_closest_marker("forked")):
            return None

        exitstatus_testexit = 4

        def runforked():
            try:
                reports = _runtestprotocol(item, log=False, nextitem=item)
            except KeyboardInterrupt:
                os._exit(exitstatus_testexit)
            return marshal.dumps([_pytest_forked.serialize_report(x) for x in reports])

        ihook = item.ihook
        ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        result = _py.process.ForkedFunc(runforked).waitfinish()
        if result.retval is not None:
            reports = [_pytest_runner.TestReport(**x) for x in marshal.loads(result.retval)]
        elif result.exitstatus == exitstatus_testexit:
            pytest.exit(f"forked test item {item} raised Exit")
        else:
            reports = [_pytest_forked.report_process_crash(item, result)]
        for rep in reports:
            ihook.pytest_runtest_logreport(report=rep)
        # The parent never ran this item's setup/teardown, so its SetupState
        # still holds whatever collectors the last unforked test left there.
        # Maintain pytest's between-items invariant ourselves: finalize the
        # collectors the next item does not need (pytest's own runtestprotocol
        # does this in teardown_exact), else the next unforked test dies with
        # "previous item was not torn down properly".
        item.session._setupstate.teardown_exact(nextitem)
        ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
        return True


@pytest.fixture(autouse=True)
def reset_pango_in_forked_children(request):
    """Make pytest-forked children safe against inherited pango state.

    Once the pytest process has rendered any text, pango's process-global
    font map owns a "[pango] fontcon" helper thread that fork() does not
    copy into children. A pytest.mark.forked test that then renders an
    as-yet-uncached font in its child deadlocks in g_cond_wait waiting for
    the missing thread, and the parent sits in waitpid() until
    pytest-timeout aborts the whole session. Drop the inherited font map so
    the child builds its own, exactly like TestManager's run_qtile() does
    for qtile children.
    """
    if request.node.get_closest_marker("forked") is not None and os.getpid() != _MAIN_PID:
        pangocffi.reset_font_map()
    yield


def pytest_addoption(parser):
    parser.addoption("--debuglog", action="store_true", default=False, help="enable debug output")
    parser.addoption(
        "--backend",
        action="append",
        choices=("x11", "wayland"),
        help="Test a specific backend. Can be passed more than once.",
    )


def pytest_cmdline_main(config):
    if not config.option.backend:
        config.option.backend = ["x11"]

    ignore = config.option.ignore or []
    if "wayland" not in config.option.backend:
        ignore.append("test/backend/wayland")
    if "x11" not in config.option.backend:
        ignore.append("test/backend/x11")
    config.option.ignore = ignore


def pytest_generate_tests(metafunc):
    if "backend" in metafunc.fixturenames:
        backends = metafunc.config.option.backend
        metafunc.parametrize("backend_name", backends)


@pytest.fixture(scope="session", params=[1])
def outputs(request):
    return request.param


dualmonitor = pytest.mark.parametrize("outputs", [2], indirect=True)
multimonitor = pytest.mark.parametrize("outputs", [1, 2], indirect=True)


@pytest.fixture(scope="session")
def xephyr(request, outputs):
    if "x11" not in request.config.option.backend:
        yield
        return

    from test.backend.x11.conftest import x11_environment

    kwargs = getattr(request, "param", {})

    with x11_environment(outputs, **kwargs) as x:
        yield x


@pytest.fixture(scope="session")
def wayland_session(request, outputs):
    if "wayland" not in request.config.option.backend:
        yield
        return

    from test.backend.wayland.conftest import wayland_environment

    with wayland_environment(outputs) as w:
        yield w


@pytest.fixture(scope="function")
def backend(request, backend_name, xephyr, wayland_session):
    if backend_name == "x11":
        from test.backend.x11.conftest import XBackend

        yield XBackend({"DISPLAY": xephyr.display}, args=[xephyr.display])
    elif backend_name == "wayland":
        from test.backend.wayland.conftest import WaylandBackend

        yield WaylandBackend(wayland_session)


@pytest.fixture(scope="function")
def manager_nospawn(request, backend):
    with TestManager(backend, request.config.getoption("--debuglog")) as manager:
        yield manager


@pytest.fixture(scope="function")
def manager(request, manager_nospawn):
    config = getattr(request, "param", BareConfig)

    manager_nospawn.start(config)
    yield manager_nospawn


@pytest.fixture(scope="function")
def fake_window():
    """
    A fake window that can provide a fake drawer to test widgets.
    """

    class FakeWindow:
        class _NestedWindow:
            wid = 10

        window = _NestedWindow()

        def create_drawer(self, width, height):
            return drawer.Drawer(self, width, height)

    return FakeWindow()


@pytest.fixture
def anyio_backend():
    return "asyncio"


# Fixture that defines a minimal configuration that has no screens.
# When used in a test, the function needs to receive a list of screens
# (including bar and widgets) as an argument. This config can then be
# passed to the manager to start.
@pytest.fixture(scope="function")
def minimal_conf_noscreen():
    class MinimalConf(libqtile.confreader.Config):
        auto_fullscreen = False
        keys = []
        mouse = []
        groups = [libqtile.config.Group("a"), libqtile.config.Group("b")]
        layouts = [libqtile.layout.stack.Stack(num_stacks=1)]
        floating_layout = libqtile.resources.default_config.floating_layout
        screens = []
        reconfigure_screens = False

    return MinimalConf
