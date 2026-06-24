import pytest

import libqtile.config
from libqtile.bar import Bar
from libqtile.confreader import Config
from libqtile.extension.window_list import WindowList
from libqtile.layout.max import Max
from libqtile.lazy import lazy


# We want the value returned immediately
def fake_popen(cmd, *args, **kwargs):
    class PopenObj:
        def communicate(self, value_in, *args):
            return [value_in, None]

    return PopenObj()


def build_window_list_config():
    # Patch Popen and build the extension in the (forkserver) qtile child so
    # the extension runs against the fake Popen when its keybinding fires.
    from libqtile.extension import base

    base.Popen = fake_popen

    extension = WindowList()

    class ManagerConfig(Config):
        groups = [
            libqtile.config.Group("a"),
            libqtile.config.Group("b"),
        ]
        layouts = [Max()]
        keys = [
            libqtile.config.Key(["control"], "k", lazy.run_extension(extension)),
        ]
        screens = [
            libqtile.config.Screen(
                bottom=Bar([], 20),
            )
        ]

    return ManagerConfig()


@pytest.fixture
def extension_manager(manager_nospawn):
    manager_nospawn.start(build_window_list_config)

    yield manager_nospawn


def test_window_list(extension_manager):
    """Test WindowList extension switches group."""

    # Launch a window and verify it's on the current group
    extension_manager.test_window("one")
    assert len(extension_manager.c.group.info()["windows"]) == 1

    # Switch group and verify no windows in group
    extension_manager.c.group["b"].toscreen()
    assert len(extension_manager.c.group.info()["windows"]) == 0

    # Toggle extension (which is patched to return immediately)
    # Check that window is visible on original group
    extension_manager.c.simulate_keypress(["control"], "k")
    assert len(extension_manager.c.group.info()["windows"]) == 1
    assert extension_manager.c.group.info()["label"] == "a"
