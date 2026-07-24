import pytest

import libqtile.confreader
from libqtile.config import Key, KeyChord
from libqtile.lazy import lazy
from libqtile.widget import Chord, base

RED = "#FF0000"
BLUE = "#00FF00"

textbox = base._TextBox("")
BASE_BACKGROUND = textbox.background
BASE_FOREGROUND = textbox.foreground


def no_op(*args):
    pass


class ChordConf(libqtile.confreader.Config):
    auto_fullscreen = False
    keys = [
        KeyChord([], "a", [Key([], "b", lazy.function(no_op))], mode="persistent_chord"),
        KeyChord(
            [],
            "z",
            [
                Key([], "b", lazy.function(no_op)),
            ],
            name="temporary_name",
        ),
        KeyChord(
            [],
            "y",
            [
                Key([], "b", lazy.function(no_op)),
            ],
            name="mode_true",
            mode=True,
        ),
        KeyChord(
            [],
            "c",
            [
                Key([], "b", lazy.function(no_op)),
            ],
            name="testcolor",
        ),
        KeyChord(
            [],
            "v",
            [
                Key([], "b", lazy.function(no_op)),
            ],
            name="test",
        ),
    ]
    mouse = []
    groups = [libqtile.config.Group("a"), libqtile.config.Group("b")]
    layouts = [libqtile.layout.stack.Stack(num_stacks=1)]
    floating_layout = libqtile.resources.default_config.floating_layout
    screens = [
        libqtile.config.Screen(
            top=libqtile.bar.Bar([Chord(chords_colors={"testcolor": (RED, BLUE)})], 10)
        )
    ]


chord_config = pytest.mark.parametrize("manager", [ChordConf], indirect=True)


@chord_config
def test_chord_widget(manager):
    widget = manager.c.widget["chord"]

    def colours():
        return (widget.eval("self.background"), widget.eval("self.layout.colour"))

    # Text is blank at start
    assert widget.info()["text"] == ""

    # Enter the "testcolor" chord
    manager.c.simulate_keypress([], "c")

    # Chord is in chords_colors so check colours
    assert widget.info()["text"] == "testcolor"
    assert colours() == (RED, BLUE)

    # Escape and enter new chord which is not in
    # chords_colors so should be default colours
    manager.c.simulate_keypress([], "Escape")
    manager.c.simulate_keypress([], "v")
    assert widget.info()["text"] == "test"
    assert colours() == (str(BASE_BACKGROUND), str(BASE_FOREGROUND))

    # Back into testcolor and custom colours
    manager.c.simulate_keypress([], "Escape")
    manager.c.simulate_keypress([], "c")
    assert widget.info()["text"] == "testcolor"
    assert colours() == (RED, BLUE)

    # Colours should reset when leaving chord
    manager.c.simulate_keypress([], "Escape")
    assert widget.info()["text"] == ""
    assert colours() == (str(BASE_BACKGROUND), str(BASE_FOREGROUND))


@chord_config
def test_chord_persistence(manager):
    widget = manager.c.widget["chord"]

    assert widget.info()["text"] == ""

    # Test 1: Test persistent chord mode name
    # Old style where mode contains text.
    # Enter the chord
    manager.c.simulate_keypress([], "a")
    assert widget.info()["text"] == "persistent_chord"

    # Chord has finished but mode should still be in place
    manager.c.simulate_keypress([], "b")
    assert widget.info()["text"] == "persistent_chord"

    # Escape to leave chord
    manager.c.simulate_keypress([], "Escape")
    assert widget.info()["text"] == ""

    # Test 2: Test persistent chord mode name
    # New style - mode = True
    # Enter the chord
    manager.c.simulate_keypress([], "y")
    assert widget.info()["text"] == "mode_true"

    # Chord has finished but mode should still be in place
    manager.c.simulate_keypress([], "b")
    assert widget.info()["text"] == "mode_true"

    # Escape to leave chord
    manager.c.simulate_keypress([], "Escape")
    assert widget.info()["text"] == ""

    # Test 3: Test temporary chord name
    # Enter the chord
    manager.c.simulate_keypress([], "z")
    assert widget.info()["text"] == "temporary_name"

    # Chord has finished and should exit
    manager.c.simulate_keypress([], "b")
    assert widget.info()["text"] == ""

    # Enter the chord
    manager.c.simulate_keypress([], "z")
    assert widget.info()["text"] == "temporary_name"

    # Escape to cancel chord
    manager.c.simulate_keypress([], "Escape")
    assert widget.info()["text"] == ""


def test_chord_mode_name_deprecation(caplog):
    chord = KeyChord([], "a", [Key([], "b", lazy.function(no_op))], mode="persistent_chord")

    assert caplog.records

    log = caplog.records[0]
    assert log.levelname == "WARNING"
    assert "name='persistent_chord'" in log.message

    # Mode should be set to True and name set to the mode name
    assert chord.mode is True
    assert chord.name == "persistent_chord"
