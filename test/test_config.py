import ast
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


def test_generate_screens_transient_output_states(
    manager_nospawn, minimal_conf_noscreen, monkeypatch, tmp_path
):
    # During a wlr-output-management transaction the backend can report a
    # series of transient output states, firing screen_change (and thus
    # reconfigure_screens) for each one. When generate_screens returns brand
    # new Screen objects every time, references held elsewhere (groups,
    # current_screen) must be rebound to the new objects and replaced bars
    # finalized, so that the final state's geometry is what everything is
    # laid out against.
    states = [
        # projector only
        [Output("HDMI-A-1", None, None, "hdmi", ScreenRect(0, 0, 3840, 2160))],
        # both monitors appear, unscaled
        [
            Output("HDMI-A-1", None, None, "hdmi", ScreenRect(0, 0, 3840, 2160)),
            Output("DP-6", None, None, "left", ScreenRect(3840, 0, 3840, 2160)),
            Output("DP-7", None, None, "right", ScreenRect(7680, 0, 3840, 2160)),
        ],
        # projector disabled
        [
            Output("DP-6", None, None, "left", ScreenRect(0, 0, 3840, 2160)),
            Output("DP-7", None, None, "right", ScreenRect(3840, 0, 3840, 2160)),
        ],
        # projector transiently re-enabled mid-transaction
        [
            Output("DP-6", None, None, "left", ScreenRect(0, 0, 3840, 2160)),
            Output("DP-7", None, None, "right", ScreenRect(3840, 0, 3840, 2160)),
            Output("HDMI-A-1", None, None, "hdmi", ScreenRect(7680, 0, 3840, 2160)),
        ],
        # final state: monitors scaled, projector off
        [
            Output("DP-6", None, None, "left", ScreenRect(0, 0, 1920, 1080)),
            Output("DP-7", None, None, "right", ScreenRect(1920, 0, 1920, 1080)),
        ],
    ]

    state_file = tmp_path / "output_state"
    state_file.write_text("0")

    def gen_screens(outputs: list[Output]) -> list[Screen]:
        # A new Screen (and Bar) object for every output on every call
        return [make_screen(text=output.port) for output in outputs]

    minimal_conf_noscreen.generate_screens = staticmethod(gen_screens)

    def read_outputs(self) -> list[Output]:
        return states[int(state_file.read_text())]

    monkeypatch.setattr(
        f"libqtile.backend.{manager_nospawn.backend.name}.core.Core.get_output_info", read_outputs
    )
    manager_nospawn.start(minimal_conf_noscreen)

    for i in range(1, len(states)):
        state_file.write_text(str(i))
        manager_nospawn.c.reconfigure_screens()

    # DP-6 and DP-7 were present in the previous state, so even though
    # generate_screens returned new Screen objects, the existing objects
    # must have been reused (with the new configuration adopted onto them)
    ids_before = ast.literal_eval(manager_nospawn.c.eval("[id(s) for s in self.screens]"))
    state_file.write_text(str(len(states) - 1))
    manager_nospawn.c.reconfigure_screens()
    ids_after = ast.literal_eval(manager_nospawn.c.eval("[id(s) for s in self.screens]"))
    assert ids_before == ids_after

    # Screens reflect the final output state
    screens = manager_nospawn.c.get_screens()
    assert len(screens) == 2
    assert manager_nospawn.c.screen[0].info()["port"] == "DP-6"
    assert manager_nospawn.c.screen[1].info()["port"] == "DP-7"
    assert (screens[0]["x"], screens[0]["y"], screens[0]["width"], screens[0]["height"]) == (
        0,
        0,
        1920,
        1080,
    )
    assert (screens[1]["x"], screens[1]["y"], screens[1]["width"], screens[1]["height"]) == (
        1920,
        0,
        1920,
        1080,
    )

    # Groups must reference the live Screen objects, not stale, replaced ones
    # that compare equal but have transient geometry
    assert manager_nospawn.c.eval("all(s.group.screen is s for s in self.screens)") == "True"

    # current_screen must be one of the live Screen objects
    current_screen_id = int(manager_nospawn.c.eval("id(self.current_screen)"))
    screen_ids = ast.literal_eval(manager_nospawn.c.eval("[id(s) for s in self.screens]"))
    assert current_screen_id in screen_ids

    # Replaced screens' bars must have been finalized: one bar window per
    # remaining screen, no leaks from earlier reconfigurations
    assert len(manager_nospawn.c.internal_windows()) == 2
