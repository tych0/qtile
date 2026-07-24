import pytest

from libqtile.widget.keyboardkbdd import KeyboardKbdd
from test.widgets.conftest import wait_for_text


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

    assert widget.eval("self.is_kbdd_running") == "True"
    wait_for_text(widget, "gb")

    # Send a signal with the index of the active keyboard
    send_signal(widget, body=1)
    wait_for_text(widget, "us")


def test_keyboardkbdd_process_not_running(kbdd_widget):
    widget = kbdd_widget(running=False)

    assert widget.eval("self.is_kbdd_running") == "False"
    wait_for_text(widget, "N/A")

    # Once kbdd is running, the next poll will confirm this
    # so widget should now show the layout
    widget.eval("type(self)._mock_ps_output = 'kbdd'")
    wait_for_text(widget, "gb")
    assert widget.eval("self.is_kbdd_running") == "True"


# Custom colours are not set until a signal is received
# TO DO: This should be fixed so the colour is set on __init__
def test_keyboard_kbdd_colours(kbdd_widget):
    widget = kbdd_widget(running=True, colours=["#ff0000", "#00ff00"])

    # Send a signal with the index of the active keyboard
    send_signal(widget, body=0)
    assert widget.eval("self.layout.colour") == "#ff0000"

    # Send a signal with the index of the active keyboard
    send_signal(widget, body=1)
    assert widget.eval("self.layout.colour") == "#00ff00"

    # No change where self.colours is a string
    widget.eval("self.colours = '#ffff00'")
    widget.eval("self._set_colour(1)")
    assert widget.eval("self.layout.colour") == "#00ff00"

    # Colours list is shorter than length of layouts
    widget.eval("self.colours = ['#ff00ff']")

    # Should pick second item in colours list but it doesn't exist
    # so widget looks for previous item
    widget.eval("self._set_colour(1)")
    assert widget.eval("self.layout.colour") == "#ff00ff"
