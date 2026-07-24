import pytest

import libqtile.bar
import libqtile.config
from libqtile.widget.keyboardkbdd import KeyboardKbdd
from test.helpers import Retry


async def mock_signal_receiver(*args, **kwargs):
    return True


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_text(widget, text):
    assert widget.info()["text"] == text


def send_signal(widget, body):
    """Simulate the dbus 'layoutChanged' signal."""
    widget.eval(
        "from types import SimpleNamespace\n"
        f"self._signal_received(SimpleNamespace(message_type=1, body=[{body}]))"
    )


@pytest.fixture
def kbdd_manager(monkeypatch, manager_nospawn, minimal_conf_noscreen):
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

        widget = KeyboardKbdd(configured_keyboards=["gb", "us"], **kwargs)

        config = minimal_conf_noscreen
        config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([widget], 10))]
        manager_nospawn.start(config)

        return manager_nospawn.c.widget["keyboardkbdd"]

    return start


def test_keyboardkbdd_process_running(kbdd_manager):
    widget = kbdd_manager(running=True)

    assert widget.eval("self.is_kbdd_running") == "True"
    wait_for_text(widget, "gb")

    # Send a signal with the index of the active keyboard
    send_signal(widget, body=1)
    wait_for_text(widget, "us")


def test_keyboardkbdd_process_not_running(kbdd_manager):
    widget = kbdd_manager(running=False)

    assert widget.eval("self.is_kbdd_running") == "False"
    wait_for_text(widget, "N/A")

    # Once kbdd is running, the next poll will confirm this
    # so widget should now show the layout
    widget.eval("type(self)._mock_ps_output = 'kbdd'")
    wait_for_text(widget, "gb")
    assert widget.eval("self.is_kbdd_running") == "True"


# Custom colours are not set until a signal is received
# TO DO: This should be fixed so the colour is set on __init__
def test_keyboard_kbdd_colours(kbdd_manager):
    widget = kbdd_manager(running=True, colours=["#ff0000", "#00ff00"])

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
