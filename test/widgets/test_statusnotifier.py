import functools
import os

import pytest

import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
import libqtile.widget
from test.helpers import Retry  # noqa: I001


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_icon(widget, hidden=True, prop="width"):
    width = widget.info()[prop]
    if hidden:
        assert width == 0
    else:
        assert width > 0


@Retry(ignore_exceptions=(AssertionError,))
def check_fullscreen(windows, fullscreen=True):
    full = windows()[0]["fullscreen"]
    assert full is fullscreen


def sni_config(param, dbus_address, vertical=False):
    """Build a config with StatusNotifier in the bar."""
    # The forkserver child doesn't inherit the session bus address set by the
    # `dbus` fixture, so it would otherwise connect to a different bus than the
    # test window publishes the SNI item on.
    if dbus_address is not None:
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = dbus_address

    bar = libqtile.bar.Bar([libqtile.widget.StatusNotifier(**param)], 50)
    if vertical:
        screen = libqtile.config.Screen(left=bar)
    else:
        screen = libqtile.config.Screen(top=bar)

    class SNIConfig(libqtile.confreader.Config):
        """Config for the test."""

        auto_fullscreen = True
        keys = []
        mouse = []
        groups = [
            libqtile.config.Group("a"),
        ]
        layouts = [libqtile.layout.Max()]
        floating_layout = libqtile.resources.default_config.floating_layout
        screens = [screen]

    return SNIConfig()


@pytest.fixture(scope="function")
def sni_config_param(request):
    """
    Fixture provides the widget kwargs used to build a StatusNotifier config.

    Widget can be customised via parameterize.
    """
    yield getattr(request, "param", dict())


@pytest.mark.usefixtures("dbus")
def test_statusnotifier_defaults(manager_nospawn, sni_config_param):
    """Check that widget displays and removes icon."""
    manager_nospawn.start(
        functools.partial(
            sni_config, sni_config_param, os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        )
    )
    widget = manager_nospawn.c.widget["statusnotifier"]
    assert widget.info()["width"] == 0

    win = manager_nospawn.test_window("TestSNI", export_sni=True)
    wait_for_icon(widget, hidden=False)

    # Kill it and icon disappears
    manager_nospawn.kill_window(win)
    wait_for_icon(widget, hidden=True)


@pytest.mark.usefixtures("dbus")
def test_statusnotifier_defaults_vertical_bar(manager_nospawn, sni_config_param):
    """Check that widget displays and removes icon."""
    manager_nospawn.start(
        functools.partial(
            sni_config,
            sni_config_param,
            os.environ.get("DBUS_SESSION_BUS_ADDRESS"),
            vertical=True,
        )
    )
    widget = manager_nospawn.c.widget["statusnotifier"]
    assert widget.info()["height"] == 0

    win = manager_nospawn.test_window("TestSNI", export_sni=True)
    wait_for_icon(widget, hidden=False, prop="height")

    # Kill it and icon disappears
    manager_nospawn.kill_window(win)
    wait_for_icon(widget, hidden=True, prop="height")


@pytest.mark.parametrize("sni_config_param", [{"icon_size": 35}], indirect=True)
@pytest.mark.usefixtures("dbus")
def test_statusnotifier_icon_size(manager_nospawn, sni_config_param):
    """Check that widget displays and removes icon."""
    manager_nospawn.start(
        functools.partial(
            sni_config, sni_config_param, os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        )
    )
    widget = manager_nospawn.c.widget["statusnotifier"]
    assert widget.info()["width"] == 0

    win = manager_nospawn.test_window("TestSNI", export_sni=True)
    wait_for_icon(widget, hidden=False)

    # Width should be icon_size (35) + 2 * padding (3) = 41
    assert widget.info()["width"] == 41

    manager_nospawn.kill_window(win)


@pytest.mark.usefixtures("dbus")
def test_statusnotifier_left_click(manager_nospawn, sni_config_param):
    """Check `activate` method when left-clicking widget."""
    manager_nospawn.start(
        functools.partial(
            sni_config, sni_config_param, os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        )
    )
    widget = manager_nospawn.c.widget["statusnotifier"]
    windows = manager_nospawn.c.windows

    assert widget.info()["width"] == 0

    win = manager_nospawn.test_window("TestSNILeftClick", export_sni=True)
    wait_for_icon(widget, hidden=False)

    # Check we have window and that it's not fullscreen
    assert len(windows()) == 1
    check_fullscreen(windows, False)

    # Left click will toggle fullscreen
    manager_nospawn.c.bar["top"].fake_button_press(10, 0, 1)
    check_fullscreen(windows, True)

    # Left click again will restore window
    manager_nospawn.c.bar["top"].fake_button_press(10, 0, 1)
    check_fullscreen(windows, False)

    manager_nospawn.kill_window(win)
    assert not windows()


@pytest.mark.usefixtures("dbus")
def test_statusnotifier_left_click_vertical_bar(manager_nospawn, sni_config_param):
    """Check `activate` method when left-clicking widget in vertical bar."""
    manager_nospawn.start(
        functools.partial(
            sni_config,
            sni_config_param,
            os.environ.get("DBUS_SESSION_BUS_ADDRESS"),
            vertical=True,
        )
    )
    widget = manager_nospawn.c.widget["statusnotifier"]
    windows = manager_nospawn.c.windows

    assert widget.info()["height"] == 0

    win = manager_nospawn.test_window("TestSNILeftClick", export_sni=True)
    wait_for_icon(widget, hidden=False, prop="height")

    # Check we have window and that it's not fullscreen
    assert len(windows()) == 1
    check_fullscreen(windows, False)

    # Left click will toggle fullscreen
    manager_nospawn.c.bar["left"].fake_button_press(0, 10, 1)
    check_fullscreen(windows, True)

    # Left click again will restore window
    manager_nospawn.c.bar["left"].fake_button_press(0, 10, 1)
    check_fullscreen(windows, False)

    manager_nospawn.kill_window(win)
    assert not windows()
