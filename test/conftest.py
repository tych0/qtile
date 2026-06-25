import pytest

import libqtile
from libqtile.backend.base import drawer
from test.helpers import BareConfig, TestManager


def pytest_addoption(parser):
    parser.addoption("--debuglog", action="store_true", default=False, help="enable debug output")
    parser.addoption(
        "--backend",
        action="append",
        choices=("x11", "wayland"),
        help="Test a specific backend. Can be passed more than once.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "decodes_image: test decodes an image in-process via libqtile.images "
        "(cairocffi.pixbuf -> glycin). glycin spins up worker threads, a D-Bus "
        "connection and a loader subprocess that fork() cannot safely carry into "
        "a child, so any qtile launched (fork()ed) afterwards would deadlock while "
        "loading an image. These tests are reordered to run after every test that "
        "launches a qtile (see pytest_collection_modifyitems).",
    )


def pytest_collection_modifyitems(config, items):
    # Run the image-decoding tests last. They leave glycin's fork-unsafe state
    # (threads/D-Bus/loader subprocess) in this process, so every test that
    # fork()s a qtile must run first, while the process is still glycin-clean.
    # The sort is stable, so the relative order within each group is preserved.
    items.sort(key=lambda item: item.get_closest_marker("decodes_image") is not None)


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


@pytest.fixture(scope="session")
def outputs(request):
    return getattr(request, "param", 1)


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
