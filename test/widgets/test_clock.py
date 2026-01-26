import datetime
import sys
from importlib import reload

import pytest

import libqtile.config
from libqtile.widget import clock
from test.widgets.conftest import FakeBar


def no_op(*args, **kwargs):
    pass


# Mock Datetime object that returns a set datetime and also
# has a simplified timezone method to check functionality of
# the widget.
class MockDatetime(datetime.datetime):
    @classmethod
    def now(cls, *args, **kwargs):
        return cls(2021, 1, 1, 10, 20, 30)

    def astimezone(self, tzone=None):
        if tzone is None:
            return self
        return self + tzone.utcoffset(None)


@pytest.fixture
def patched_clock(monkeypatch):
    # Stop system importing dateutil in case it exists on environment
    monkeypatch.setitem(sys.modules, "dateutil", None)
    monkeypatch.setitem(sys.modules, "dateutil.tz", None)

    # Reload module to force ImportErrors
    reload(clock)

    # Override datetime.
    # This is key for testing as we can fix time.
    monkeypatch.setattr("libqtile.widget.clock.datetime", MockDatetime)


def test_clock(fake_qtile, monkeypatch, fake_window):
    """test clock output with default settings"""
    monkeypatch.setattr("libqtile.widget.clock.datetime", MockDatetime)
    clk1 = clock.Clock()
    fakebar = FakeBar([clk1], window=fake_window)
    clk1._configure(fake_qtile, fakebar)
    text = clk1.poll()
    assert text == "10:20"


@pytest.mark.usefixtures("patched_clock")
def test_clock_invalid_timezone(fake_qtile, monkeypatch, fake_window, caplog):
    """test clock widget with invalid timezone string"""

    # dateutil must not be in the sys.modules dict...
    monkeypatch.delitem(sys.modules, "dateutil")

    # Set up reference to dateutil so we know it isn't being used
    clock.dateutil = None

    # Use an invalid timezone string that will cause ZoneInfo to raise KeyError
    clk2 = clock.Clock(timezone="Invalid/Timezone")

    fakebar = FakeBar([clk2], window=fake_window)
    clk2._configure(fake_qtile, fakebar)

    # An invalid timezone results in a log message
    assert "Unknown timezone: Invalid/Timezone" in caplog.text


@pytest.mark.usefixtures("patched_clock")
def test_clock_datetime_timezone(fake_qtile, monkeypatch, fake_window):
    """test clock with datetime timezone"""

    # Fake datetime module just adds the timezone value to the time
    tz = datetime.timezone(datetime.timedelta(hours=1))
    clk3 = clock.Clock(timezone=tz)

    fakebar = FakeBar([clk3], window=fake_window)
    clk3._configure(fake_qtile, fakebar)
    text = clk3.poll()

    # Default time is 10:20 and we add 1 hour for the timezone
    assert text == "11:20"


@pytest.mark.usefixtures("patched_clock")
def test_clock_zoneinfo_timezone(fake_qtile, monkeypatch, fake_window):
    """test clock with zoneinfo timezone string"""

    class FakeZoneInfo:
        """Fake ZoneInfo that returns a fixed offset for testing"""

        def __init__(self, key):
            # Convert the timezone key to an offset for testing
            # Using a simple mapping: "1" -> +2 hours (to show zoneinfo is used)
            self._offset = datetime.timedelta(hours=int(key) + 1)

        def utcoffset(self, dt):
            return self._offset

    # Replace ZoneInfo with our fake
    monkeypatch.setattr("libqtile.widget.clock.ZoneInfo", FakeZoneInfo)

    # Timezone must be a string
    clk4 = clock.Clock(timezone="1")

    fakebar = FakeBar([clk4], window=fake_window)
    clk4._configure(fake_qtile, fakebar)
    text = clk4.poll()

    # Default time is 10:20 and we add 1 hour for the timezone plus an extra
    # 1 for the FakeZoneInfo function
    assert text == "12:20"


@pytest.mark.usefixtures("patched_clock")
def test_clock_dateutil_fallback(fake_qtile, monkeypatch, fake_window):
    """test clock falls back to dateutil when zoneinfo fails"""

    class FakeDateutilTZ:
        class TZ:
            @classmethod
            def gettz(cls, val):
                hours = int(val) + 2
                return datetime.timezone(datetime.timedelta(hours=hours))

        tz = TZ

    class FailingZoneInfo:
        """ZoneInfo that always raises KeyError to test dateutil fallback"""

        def __init__(self, key):
            raise KeyError(f"Unknown timezone: {key}")

    # dateutil must be in sys.modules
    monkeypatch.setitem(sys.modules, "dateutil", True)

    # Replace ZoneInfo with one that fails
    monkeypatch.setattr("libqtile.widget.clock.ZoneInfo", FailingZoneInfo)

    # Set up dateutil as fallback
    clock.dateutil = FakeDateutilTZ

    # Timezone as a string
    clk5 = clock.Clock(timezone="1")

    fakebar = FakeBar([clk5], window=fake_window)
    clk5._configure(fake_qtile, fakebar)
    text = clk5.poll()

    # Default time is 10:20 and we add 1 hour for the timezone plus an extra
    # 2 for the dateutil function
    assert text == "13:20"


@pytest.mark.usefixtures("patched_clock")
def test_clock_tick(manager_nospawn, minimal_conf_noscreen, monkeypatch):
    """Test clock ticks"""

    class TickingDateTime(datetime.datetime):
        offset = 0

        @classmethod
        def now(cls, *args, **kwargs):
            return cls(2021, 1, 1, 10, 20, 30)

        # This will return 10:20 on first call and 10:21 on all
        # subsequent calls
        def astimezone(self, tzone=None):
            extra = datetime.timedelta(minutes=TickingDateTime.offset)
            if TickingDateTime.offset < 1:
                TickingDateTime.offset += 1

            if tzone is None:
                return self + extra
            return self + extra

    # Override datetime
    monkeypatch.setattr("libqtile.widget.clock.datetime", TickingDateTime)

    # set a long update interval as we'll tick manually
    clk6 = clock.Clock(update_interval=100)

    config = minimal_conf_noscreen
    config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([clk6], 10))]

    manager_nospawn.start(config)

    topbar = manager_nospawn.c.bar["top"]
    manager_nospawn.c.widget["clock"].eval("self.tick()")
    assert topbar.info()["widgets"][0]["text"] == "10:21"


@pytest.mark.usefixtures("patched_clock")
def test_clock_change_timezones(fake_qtile, monkeypatch, fake_window):
    """test commands to change timezones"""

    tz1 = datetime.timezone(datetime.timedelta(hours=1))
    tz2 = datetime.timezone(-datetime.timedelta(hours=1))

    clk4 = clock.Clock(timezone=tz1)

    fakebar = FakeBar([clk4], window=fake_window)
    clk4._configure(fake_qtile, fakebar)
    text = clk4.poll()
    assert text == "11:20"

    clk4.update_timezone(tz2)
    text = clk4.poll()
    assert text == "09:20"

    clk4.use_system_timezone()
    text = clk4.poll()
    assert text == "10:20"
