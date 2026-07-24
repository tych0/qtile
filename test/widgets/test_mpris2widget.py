import sys
from importlib import reload
from types import ModuleType

import pytest

TRACK = "Never Gonna Give You Up - Whenever You Need Somebody - Rick Astley"


async def mock_signal_receiver(*args, **kwargs):
    return True


class MockConstants(ModuleType):
    class MessageType:
        SIGNAL = 1


# dbus_fast message data is stored in variants. The widget extracts the
# information via the `value` attribute so we just mock that in the
# qtile process via `eval` calls.
METADATA = (
    '{"Metadata": V({'
    '"mpris:trackid": V(1), '
    '"xesam:url": V("/path/to/rickroll.mp3"), '
    '"xesam:title": V("Never Gonna Give You Up"), '
    '"xesam:artist": V(["Rick Astley"]), '
    '"xesam:album": V("Whenever You Need Somebody"), '
    '"mpris:length": V(200000000)})'
)


def parse_message(widget, status, metadata=False):
    """Simulate the widget receiving a dbus signal message."""
    if metadata:
        changed = METADATA + f', "PlaybackStatus": V("{status}")}}'
    else:
        changed = f'{{"PlaybackStatus": V("{status}")}}'

    widget.eval(
        "class V:\n"
        "    def __init__(self, value):\n"
        "        self.value = value\n"
        f"self.parse_message('', {changed}, [])"
    )


@pytest.fixture
def patched_module(monkeypatch):
    # Remove dbus_fast.constants entry from modules. If it's not there, don't raise error
    monkeypatch.delitem(sys.modules, "dbus_fast.constants", raising=False)
    monkeypatch.setitem(sys.modules, "dbus_fast.constants", MockConstants("dbus_fast.constants"))
    from libqtile.widget import mpris2widget

    # Need to force reload of the module to ensure patched module is loaded
    # This may only be needed if dbus_fast is installed on testing system so helpful for
    # local tests.
    reload(mpris2widget)
    monkeypatch.setattr("libqtile.widget.mpris2widget.add_signal_receiver", mock_signal_receiver)
    return mpris2widget


@pytest.fixture
def mpris_widget(patched_module, widget_manager):
    def start(**kwargs):
        return widget_manager(patched_module.Mpris2(**kwargs))

    return start


def test_mpris2_signal_handling(mpris_widget):
    mp = mpris_widget()

    assert mp.eval("self.displaytext") == ""

    # No text will be displayed if widget is not configured
    mp.eval("self.configured = False")
    parse_message(mp, "Playing", metadata=True)
    assert mp.eval("self.displaytext") == ""

    # Set configured flag, create a message with the metadata and playback status
    mp.eval("self.configured = True")
    parse_message(mp, "Playing", metadata=True)
    assert mp.eval("self.text") == TRACK

    # If widget receives "paused" signal it prefixes track with "Paused: "
    parse_message(mp, "Paused")
    assert mp.eval("self.text") == f"Paused: {TRACK}"

    # If widget receives "stopped" signal with no metadata then widget is blank
    parse_message(mp, "Stopped")
    assert mp.eval("self.displaytext") == ""

    # Reset to playing + metadata
    parse_message(mp, "Playing", metadata=True)
    assert mp.eval("self.text") == TRACK

    # If widget receives "paused" signal with metadata then message is "Paused: {metadata}"
    parse_message(mp, "Paused", metadata=True)
    assert mp.eval("self.text") == f"Paused: {TRACK}"

    # If widget now receives "playing" signal with no metadata, "paused" word is removed
    parse_message(mp, "Playing")
    assert mp.eval("self.text") == TRACK

    info = mp.info()
    assert info["text"] == TRACK
    assert info["isplaying"]


def test_mpris2_custom_stop_text(mpris_widget):
    mp = mpris_widget(stop_pause_text="Test Paused")

    parse_message(mp, "Playing", metadata=True)
    assert mp.eval("self.text") == TRACK

    # Check our custom paused wording is shown
    parse_message(mp, "Paused")
    assert mp.eval("self.text") == "Test Paused"


def test_mpris2_no_metadata(mpris_widget):
    mp = mpris_widget()

    parse_message(mp, "Playing")
    assert mp.eval("self.text") == "No metadata for current track"


def test_mpris2_no_scroll(mpris_widget):
    # If no scrolling, then the update function creates the text to display
    # and draws the bar.
    mp = mpris_widget(scroll_chars=None)

    parse_message(mp, "Playing", metadata=True)
    assert mp.eval("self.text") == TRACK

    parse_message(mp, "Paused", metadata=True)
    assert mp.eval("self.text") == f"Paused: {TRACK}"


def test_mpris2_deprecated_format(patched_module):
    """
    Previously, metadata was displayed by using a list of fields.
    Now, we use a `format` string. The widget should create this when a user
    provides `display_metadata` in their config.
    """
    mp = patched_module.Mpris2(display_metadata=["xesam:title", "xesam:artist"])
    assert mp.format == "{xesam:title} - {xesam:artist}"
