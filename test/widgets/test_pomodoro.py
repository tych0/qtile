from datetime import datetime, timedelta

import pytest

import libqtile.bar
import libqtile.config
from libqtile.widget import pomodoro

COLOR_INACTIVE = "123456"
COLOR_ACTIVE = "654321"
COLOR_BREAK = "AABBCC"
PREFIX_INACTIVE = "TESTING POMODORO"
PREFIX_ACTIVE = "ACTIVE"
PREFIX_BREAK = "BREAK"
PREFIX_LONG_BREAK = "LONG BREAK"
PREFIX_PAUSED = "PAUSING"


# Mock Datetime object that returns a set datetime but can
# be adjusted via the '_adjustment' property
class MockDatetime(datetime):
    _adjustment = timedelta(0)

    @classmethod
    def now(cls, *args, **kwargs):
        return cls(2021, 1, 1, 12, 00, 0) + cls._adjustment


@pytest.fixture
def pomodoro_manager(monkeypatch, manager_nospawn, minimal_conf_noscreen):
    MockDatetime._adjustment = timedelta(0)
    monkeypatch.setattr("libqtile.widget.pomodoro.datetime", MockDatetime)

    widget = pomodoro.Pomodoro(
        update_interval=100,
        color_active=COLOR_ACTIVE,
        color_inactive=COLOR_INACTIVE,
        color_break=COLOR_BREAK,
        num_pomodori=2,
        length_pomodori=15,
        length_short_break=5,
        length_long_break=10,
        notification_on=False,
        prefix_inactive=PREFIX_INACTIVE,
        prefix_active=PREFIX_ACTIVE,
        prefix_break=PREFIX_BREAK,
        prefix_long_break=PREFIX_LONG_BREAK,
        prefix_paused=PREFIX_PAUSED,
    )

    config = minimal_conf_noscreen
    config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([widget], 10))]
    manager_nospawn.start(config)

    yield manager_nospawn.c.widget["pomodoro"]


def advance_time(widget, minutes):
    """Move the mocked clock forward by the given number of minutes."""
    widget.eval(
        "from datetime import timedelta\n"
        "from libqtile.widget import pomodoro\n"
        f"pomodoro.datetime._adjustment += timedelta(minutes={minutes})"
    )


def test_pomodoro(pomodoro_manager):
    widget = pomodoro_manager

    # When we start, widget is inactive
    assert widget.eval("self.poll()") == PREFIX_INACTIVE
    assert widget.eval("self.layout.colour") == COLOR_INACTIVE

    # Left clicking toggles state
    widget.toggle_break()
    assert widget.eval("self.poll()") == f"{PREFIX_ACTIVE}0:15:00"
    assert widget.eval("self.layout.colour") == COLOR_ACTIVE

    # Another left click should pause
    widget.toggle_break()
    assert widget.eval("self.poll()") == PREFIX_PAUSED
    assert widget.eval("self.layout.colour") == COLOR_INACTIVE

    widget.toggle_break()
    # Add 5 mins should take 5 mins off our timer
    advance_time(widget, 5)
    assert widget.eval("self.poll()") == f"{PREFIX_ACTIVE}0:10:00"
    assert widget.eval("self.layout.colour") == COLOR_ACTIVE

    # Add 10 mins should take us to end of first pomodoro
    # So we get a short break between pomodori
    advance_time(widget, 10)
    assert widget.eval("self.poll()") == f"{PREFIX_BREAK}0:05:00"
    assert widget.eval("self.layout.colour") == COLOR_BREAK

    # Add 5 mins should take us to start of second pomodoro
    advance_time(widget, 5)
    assert widget.eval("self.poll()") == f"{PREFIX_ACTIVE}0:15:00"
    assert widget.eval("self.layout.colour") == COLOR_ACTIVE

    # Add 15 mins should take us to end of second pomodoro
    # and start of long break (as there are only two pomodori)
    advance_time(widget, 15)
    assert widget.eval("self.poll()") == f"{PREFIX_LONG_BREAK}0:10:00"
    assert widget.eval("self.layout.colour") == COLOR_BREAK

    # Move forward so we're at start of next pomodoro
    advance_time(widget, 10)
    assert widget.eval("self.poll()") == f"{PREFIX_ACTIVE}0:15:00"

    # Advance into pomodoro
    advance_time(widget, 10)
    assert widget.eval("self.poll()") == f"{PREFIX_ACTIVE}0:05:00"

    # Right-click toggles active state
    widget.toggle_active()
    assert widget.eval("self.poll()") == PREFIX_INACTIVE

    # Right-click again resets status
    widget.toggle_active()
    assert widget.eval("self.poll()") == f"{PREFIX_ACTIVE}0:15:00"
