from pathlib import Path

import pytest

from libqtile import config, confreader, utils
from libqtile.bar import Bar
from libqtile.config import Output, Screen, ScreenRect
from libqtile.widget import TextBox

configs_dir = Path(__file__).resolve().parent / "configs"


def load_config(name):
    f = confreader.Config(configs_dir / name)
    f.load()
    return f


def test_validate():
    # bad key
    f = load_config("basic.py")
    f.keys[0].key = "nonexistent"
    with pytest.raises(confreader.ConfigError):
        f.validate()

    # bad modifier
    f = load_config("basic.py")
    f.keys[0].modifiers = ["nonexistent"]
    with pytest.raises(confreader.ConfigError):
        f.validate()


def test_basic():
    f = load_config("basic.py")
    assert f.keys


def test_syntaxerr():
    with pytest.raises(SyntaxError):
        load_config("syntaxerr.py")


def test_falls_back():
    f = load_config("basic.py")
    # We just care that it has a default, we don't actually care what the
    # default is; don't assert anything at all about the default in case
    # someone changes it down the road.
    assert hasattr(f, "follow_mouse_focus")


def cmd(x):
    return None


def test_ezkey():
    key = config.EzKey("M-A-S-a", cmd, cmd)
    modkey, altkey = (config.EzConfig.modifier_keys[i] for i in "MA")
    assert key.modifiers == [modkey, altkey, "shift"]
    assert key.key == "a"
    assert key.commands == (cmd, cmd)

    key = config.EzKey("M-<Tab>", cmd)
    assert key.modifiers == [modkey]
    assert key.key == "Tab"
    assert key.commands == (cmd,)

    with pytest.raises(utils.QtileError):
        config.EzKey("M--", cmd)

    with pytest.raises(utils.QtileError):
        config.EzKey("Z-Z-z", cmd)

    with pytest.raises(utils.QtileError):
        config.EzKey("asdf", cmd)

    with pytest.raises(utils.QtileError):
        config.EzKey("M-a-A", cmd)


def test_ezclick_ezdrag():
    btn = config.EzClick("M-1", cmd)
    assert btn.button == "Button1"
    assert btn.modifiers == [config.EzClick.modifier_keys["M"]]

    btn = config.EzDrag("A-2", cmd)
    assert btn.button == "Button2"
    assert btn.modifiers == [config.EzClick.modifier_keys["A"]]


def test_screen_underbar_methods():
    one = config.Screen(x=10, y=10, width=10, height=10)
    two = config.Screen(x=20, y=20, width=20, height=20)

    assert hash(one) != hash(two)
    assert hash(one) == hash(one)
    assert one != two
    assert one == one


def test_screen_serial_ordering_the_order(manager_nospawn, minimal_conf_noscreen, monkeypatch):
    # no serial numbers in config is ordered in config order
    minimal_conf_noscreen.screens = [Screen(), Screen()]

    def the_order(self) -> list[Output]:
        return [
            Output(None, None, None, "a", ScreenRect(0, 0, 800, 600)),
            Output(None, None, None, "b", ScreenRect(800, 0, 800, 600)),
        ]

    monkeypatch.setattr(
        f"libqtile.backend.{manager_nospawn.backend.name}.core.Core.get_output_info", the_order
    )
    manager_nospawn.start(minimal_conf_noscreen)
    assert manager_nospawn.c.screen[0].info()["serial"] == "a"
    assert manager_nospawn.c.screen[1].info()["serial"] == "b"


def make_screen(text: str = "") -> Screen:
    screen = Screen(top=Bar([TextBox(text)], 10))
    return screen


def test_generate_screens_too_few(manager_nospawn, minimal_conf_noscreen, monkeypatch):
    # generate_screens returns fewer screens than outputs; extra outputs should
    # get default Screen() objects
    def gen_screens(outputs: list[Output]) -> list[Screen]:
        # Only return one screen even though there are two outputs
        return [make_screen(text="first")]

    minimal_conf_noscreen.generate_screens = staticmethod(gen_screens)

    def two_outputs(self) -> list[Output]:
        return [
            Output("DP-1", None, None, "serial_a", ScreenRect(0, 0, 800, 600)),
            Output("DP-2", None, None, "serial_b", ScreenRect(800, 0, 800, 600)),
        ]

    monkeypatch.setattr(
        f"libqtile.backend.{manager_nospawn.backend.name}.core.Core.get_output_info", two_outputs
    )
    manager_nospawn.start(minimal_conf_noscreen)

    # First screen should use the generated screen config
    assert manager_nospawn.c.screen[0].bar["top"].widget["textbox"].get() == "first"
    assert manager_nospawn.c.screen[0].info()["serial"] == "serial_a"

    # Second screen should be a default Screen (auto-created, no custom bar)
    assert manager_nospawn.c.screen[1].info()["serial"] == "serial_b"
    # Verify both screens exist
    assert len(manager_nospawn.c.get_screens()) == 2


def test_generate_screens_too_many(manager_nospawn, minimal_conf_noscreen, monkeypatch):
    # generate_screens returns more screens than outputs; extra screens should
    # be ignored
    def gen_screens(outputs: list[Output]) -> list[Screen]:
        # Return three screens even though there's only one output
        return [
            make_screen(text="first"),
            make_screen(text="second"),
            make_screen(text="third"),
        ]

    minimal_conf_noscreen.generate_screens = staticmethod(gen_screens)

    def one_output(self) -> list[Output]:
        return [
            Output("DP-1", None, None, "serial_a", ScreenRect(0, 0, 800, 600)),
        ]

    monkeypatch.setattr(
        f"libqtile.backend.{manager_nospawn.backend.name}.core.Core.get_output_info", one_output
    )
    manager_nospawn.start(minimal_conf_noscreen)

    # Only one screen should exist (matching the single output)
    assert len(manager_nospawn.c.get_screens()) == 1
    assert manager_nospawn.c.screen[0].bar["top"].widget["textbox"].get() == "first"
    assert manager_nospawn.c.screen[0].info()["serial"] == "serial_a"


def test_generate_screens_serial_matching(manager_nospawn, minimal_conf_noscreen, monkeypatch):
    # generate_screens can inspect output serial numbers and return screens
    # in a specific order based on them
    def gen_screens(outputs: list[Output]) -> list[Screen]:
        screens = []
        for output in outputs:
            if output.serial == "monitor_left":
                screens.append(make_screen(text="left_config"))
            elif output.serial == "monitor_right":
                screens.append(make_screen(text="right_config"))
            else:
                screens.append(Screen())
        return screens

    minimal_conf_noscreen.generate_screens = staticmethod(gen_screens)

    def two_outputs(self) -> list[Output]:
        return [
            Output("DP-1", None, None, "monitor_left", ScreenRect(0, 0, 800, 600)),
            Output("DP-2", None, None, "monitor_right", ScreenRect(800, 0, 800, 600)),
        ]

    monkeypatch.setattr(
        f"libqtile.backend.{manager_nospawn.backend.name}.core.Core.get_output_info", two_outputs
    )
    manager_nospawn.start(minimal_conf_noscreen)

    # Verify screens got the correct config based on their serial number
    assert manager_nospawn.c.screen[0].bar["top"].widget["textbox"].get() == "left_config"
    assert manager_nospawn.c.screen[0].info()["serial"] == "monitor_left"
    assert manager_nospawn.c.screen[1].bar["top"].widget["textbox"].get() == "right_config"
    assert manager_nospawn.c.screen[1].info()["serial"] == "monitor_right"


def test_generate_screens_reuses_existing_screens(
    manager_nospawn, minimal_conf_noscreen, monkeypatch
):
    # When screens are reconfigured, and generate_screens returns a new Screen
    # object for an existing output, the existing Screen object must be reused
    # (with the new configuration adopted onto it)
    minimal_conf_noscreen.generate_screens = staticmethod(
        lambda outputs: [make_screen(text=o.port) for o in outputs]
    )

    def two_outputs(self) -> list[Output]:
        # DP-1 is always present; the second output can be swapped from the test
        second = getattr(self, "second_port", "DP-2")
        return [
            Output("DP-1", None, None, None, ScreenRect(0, 0, 800, 600)),
            Output(second, None, None, None, ScreenRect(800, 0, 800, 600)),
        ]

    monkeypatch.setattr(
        f"libqtile.backend.{manager_nospawn.backend.name}.core.Core.get_output_info", two_outputs
    )
    manager_nospawn.start(minimal_conf_noscreen)

    assert manager_nospawn.c.screen[0].info()["port"] == "DP-1"
    assert manager_nospawn.c.screen[1].info()["port"] == "DP-2"
    assert manager_nospawn.c.screen.info()["index"] == 0

    screen_0_id_before = manager_nospawn.c.eval("id(self.screens[0])")
    screen_1_id_before = manager_nospawn.c.eval("id(self.screens[1])")
    current_screen_id_before = manager_nospawn.c.eval("id(self.current_screen)")

    # Swap DP-2 for DP-3, then reconfigure
    manager_nospawn.c.eval("setattr(self.core, 'second_port', 'DP-3')")
    manager_nospawn.c.reconfigure_screens()

    assert manager_nospawn.c.screen[0].info()["port"] == "DP-1"
    assert manager_nospawn.c.screen[1].info()["port"] == "DP-3"

    screen_0_id_after = manager_nospawn.c.eval("id(self.screens[0])")
    screen_1_id_after = manager_nospawn.c.eval("id(self.screens[1])")
    assert screen_0_id_after == screen_0_id_before  # DP-1 reused
    assert screen_1_id_after != screen_1_id_before  # DP-2 -> DP-3, new Screen

    # Groups must reference live Screen objects
    assert manager_nospawn.c.eval("all(s.group.screen is s for s in self.screens)") == "True"

    # current_screen object hasn't changed
    assert manager_nospawn.c.eval("id(self.current_screen)") == current_screen_id_before

    # Replaced screens' bars must have been finalized: one bar window per
    # remaining screen, no leaks from reconfigure
    assert len(manager_nospawn.c.internal_windows()) == 2


@pytest.fixture
def migration_dir(tmp_path):
    pytest.importorskip("libcst")
    import sys
    import uuid

    suffix = uuid.uuid4().hex
    names = {"config": f"automigrate_config_{suffix}", "helper": f"automigrate_helper_{suffix}"}
    yield tmp_path, names
    for name in names.values():
        sys.modules.pop(name, None)
    while tmp_path.as_posix() in sys.path:
        sys.path.remove(tmp_path.as_posix())


def test_auto_migrate_success(migration_dir):
    from libqtile.scripts.migrate import BACKUP_SUFFIX

    tmp_path, names = migration_dir
    # The outdated import lives in a submodule, to check those get migrated too.
    helper = tmp_path / f"{names['helper']}.py"
    helper_src = "from libqtile.widget.base import UNSPECIFIED\nvalue = 42\n"
    helper.write_text(helper_src)
    config_file = tmp_path / f"{names['config']}.py"
    config_src = f"from {names['helper']} import value\nwmname = str(value)\n"
    config_file.write_text(config_src)

    f = confreader.Config(config_file)
    with pytest.raises(confreader.ConfigMigrated):
        f.load()
    # what a re-exec'd qtile would do
    f = confreader.Config(config_file)
    f.load()
    assert f.wmname == "42"

    # migrated file is written back, with a backup of the original
    assert "UNSPECIFIED" not in helper.read_text()
    assert (tmp_path / (helper.name + BACKUP_SUFFIX)).read_text() == helper_src
    assert not (tmp_path / confreader.MIGRATE_SUBDIR).exists()
    # modules point at the real files, not the scratch dir
    import sys

    assert sys.modules[names["helper"]].__file__ == str(helper)
    # unchanged files are left alone
    assert config_file.read_text() == config_src
    assert not (tmp_path / (config_file.name + BACKUP_SUFFIX)).exists()


def test_auto_migrate_still_broken(migration_dir):
    tmp_path, names = migration_dir
    config_file = tmp_path / f"{names['config']}.py"
    src = "from libqtile.widget.base import UNSPECIFIED\nraise RuntimeError('broken')\n"
    config_file.write_text(src)

    f = confreader.Config(config_file)
    with pytest.raises(ImportError):
        f.load()

    # the migrated config didn't load, so nothing is written back
    assert config_file.read_text() == src
    assert not list(tmp_path.glob("*.bak"))
    assert not (tmp_path / confreader.MIGRATE_SUBDIR).exists()


def test_auto_migrate_disabled(migration_dir):
    tmp_path, names = migration_dir
    config_file = tmp_path / f"{names['config']}.py"
    src = "from libqtile.widget.base import UNSPECIFIED\n"
    config_file.write_text(src)

    f = confreader.Config(config_file)
    with pytest.raises(ImportError):
        f.load(auto_migrate=False)
    assert config_file.read_text() == src


def test_auto_migrate_on_reload(migration_dir):
    tmp_path, names = migration_dir
    config_file = tmp_path / f"{names['config']}.py"
    config_file.write_text("wmname = 'one'\n")

    f = confreader.Config(config_file)
    f.load()
    assert f.wmname == "one"

    config_file.write_text("from libqtile.widget.base import UNSPECIFIED\nwmname = 'two'\n")
    with pytest.raises(confreader.ConfigMigrated):
        f.load()
    # e.g. a backend that can't restart loads the migrated config in place
    f.load(auto_migrate=False)
    assert f.wmname == "two"
    assert "UNSPECIFIED" not in config_file.read_text()

    # and later reloads keep picking up edits to the real file
    config_file.write_text("wmname = 'three'\n")
    f.load()
    assert f.wmname == "three"
