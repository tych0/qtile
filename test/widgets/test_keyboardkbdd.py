import pytest

from libqtile.widget.keyboardkbdd import KeyboardKbdd
from test.widgets.conftest import wait_for_eval, wait_for_text


async def mock_signal_receiver(*args, **kwargs):
    return True


def send_signal(widget, body):
    """Simulate the dbus 'layoutChanged' signal."""
    widget.eval(
        "from types import SimpleNamespace\n"
        f"self._signal_received(SimpleNamespace(message_type=1, body=[{body}]))"
    )


@pytest.fixture
def kbdd_widget(monkeypatch, widget_manager):
    def start(running, **kwargs):
        # The widget calls `ps` to check whether kbdd is running. Fake the
        # output so the tests don't rely on the state of the host: the
        # output is read from a class attribute which tests can update via
        # `eval` calls in the qtile process.
        monkeypatch.setattr(
            "libqtile.widget.keyboardkbdd.KeyboardKbdd._mock_ps_output",
            "kbdd" if running else "",
            raising=False,
        )
        monkeypatch.setattr(
            "libqtile.widget.keyboardkbdd.KeyboardKbdd.call_process",
            lambda self, *args, **kw: self._mock_ps_output,
        )
        monkeypatch.setattr(
            "libqtile.widget.keyboardkbdd.add_signal_receiver", mock_signal_receiver
        )

        return widget_manager(KeyboardKbdd(configured_keyboards=["gb", "us"], **kwargs))

    return start


def test_keyboardkbdd_process_running(kbdd_widget):
    widget = kbdd_widget(running=True)
    wait_for_text(widget, "gb")

    # Send a signal with the index of the active keyboard
    send_signal(widget, body=1)
    wait_for_text(widget, "us")


def test_keyboardkbdd_process_not_running(kbdd_widget):
    widget = kbdd_widget(running=False)
    wait_for_text(widget, "N/A")

    # Once kbdd is running, the next poll will confirm this
    # so widget should now show the layout
    widget.eval("type(self)._mock_ps_output = 'kbdd'")
    wait_for_text(widget, "gb")


# Custom colours are not set until a signal is received
# TO DO: This should be fixed so the colour is set on __init__
def test_keyboard_kbdd_colours(kbdd_widget):
    widget = kbdd_widget(running=True, colours=["#ff0000", "#00ff00"])

    # Send a signal with the index of the active keyboard
    send_signal(widget, body=0)
    wait_for_eval(widget, "self.layout.colour", "#ff0000")

    # Send a signal with the index of the active keyboard
    send_signal(widget, body=1)
    wait_for_eval(widget, "self.layout.colour", "#00ff00")


def test_keyboard_kbdd_colours_not_a_list(kbdd_widget):
    """Where colours is a string, the colour is not changed."""
    widget = kbdd_widget(running=True, colours="#ffff00")
    default_colour = widget.eval("self.layout.colour")

    send_signal(widget, body=1)
    wait_for_text(widget, "us")
    assert widget.eval("self.layout.colour") == default_colour


def test_keyboard_kbdd_colours_short_list(kbdd_widget):
    """Where the colours list is too short, the last colour is used."""
    widget = kbdd_widget(running=True, colours=["#ff00ff"])

    # Should pick second item in colours list but it doesn't exist
    # so widget looks for previous item
    send_signal(widget, body=1)
    wait_for_text(widget, "us")
    wait_for_eval(widget, "self.layout.colour", "#ff00ff")
