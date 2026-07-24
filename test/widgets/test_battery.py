import pytest

from libqtile import images
from libqtile.widget import battery
from libqtile.widget.battery import Battery, BatteryIcon, BatteryState, BatteryStatus
from test.widgets.conftest import TEST_DIR, wait_for_eval


def set_battery_status(widget, state, percent):
    """Update the dummy battery's status and repoll the widget."""
    widget.eval(
        "from libqtile.widget.battery import BatteryStatus, BatteryState\n"
        "self._battery._status = BatteryStatus(\n"
        f"    state=BatteryState.{state},\n"
        f"    percent={percent},\n"
        "    power=15.0,\n"
        "    time=1729,\n"
        "    charge_start_threshold=0,\n"
        "    charge_end_threshold=100,\n"
        ")"
    )
    widget.force_update()


class DummyBattery:
    def __init__(self, status):
        self._status = status

    def update_status(self):
        return self._status


class DummyErrorBattery:
    def __init__(self, **config):
        pass

    def update_status(self):
        raise RuntimeError("err")


def dummy_load_battery(bat):
    def load_battery(**config):
        return DummyBattery(bat)

    return load_battery


def test_text_battery_charging(monkeypatch):
    loaded_bat = BatteryStatus(
        state=BatteryState.CHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery()

    text = batt.poll()
    assert text == "^ 50% 0:28 15.00 W"


def test_text_battery_discharging(monkeypatch):
    loaded_bat = BatteryStatus(
        state=BatteryState.DISCHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery()

    text = batt.poll()
    assert text == "V 50% 0:28 15.00 W"


def test_text_battery_full(monkeypatch):
    loaded_bat = BatteryStatus(
        state=BatteryState.FULL,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery()

    text = batt.poll()
    assert text == "Full"

    full_short_text = "🔋"
    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(full_short_text=full_short_text)

    text = batt.poll()
    assert text == full_short_text

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(show_short_text=False)

    text = batt.poll()
    assert text == "= 50% 0:28 15.00 W"


def test_text_battery_empty(monkeypatch):
    loaded_bat = BatteryStatus(
        state=BatteryState.EMPTY,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery()

    text = batt.poll()
    assert text == "Empty"

    empty_short_text = "🪫"
    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(empty_short_text=empty_short_text)

    text = batt.poll()
    assert text == empty_short_text

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(show_short_text=False)

    text = batt.poll()
    assert text == "x 50% 0:28 15.00 W"

    loaded_bat = BatteryStatus(
        state=BatteryState.UNKNOWN,
        percent=0.0,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery()

    text = batt.poll()
    assert text == "Empty"


def test_text_battery_not_charging(monkeypatch):
    loaded_bat = BatteryStatus(
        state=BatteryState.NOT_CHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery()

    text = batt.poll()
    assert text == "* 50% 0:28 15.00 W"


def test_text_battery_unknown(monkeypatch):
    loaded_bat = BatteryStatus(
        state=BatteryState.UNKNOWN,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery()

    text = batt.poll()
    assert text == "? 50% 0:28 15.00 W"


def test_text_battery_hidden(monkeypatch):
    loaded_bat = BatteryStatus(
        state=BatteryState.DISCHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(hide_threshold=0.6)

    text = batt.poll()
    assert text != ""

    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(hide_threshold=0.4)

    text = batt.poll()
    assert text == ""


def test_text_battery_error(monkeypatch):
    with monkeypatch.context() as manager:
        manager.setattr(battery, "load_battery", DummyErrorBattery)
        batt = Battery()

    text = batt.poll()
    assert text == "Error: err"


def test_images_fail():
    """Test BatteryIcon() with a bad theme_path

    This theme path doesn't contain all of the required images.
    """
    batt = BatteryIcon(theme_path=TEST_DIR)
    with pytest.raises(images.LoadingError):
        batt.setup_images()


def test_images_good(tmpdir, svg_img_as_pypath, widget_manager, monkeypatch):
    """Test BatteryIcon() with a good theme_path

    This theme path does contain all of the required images.
    """
    for name in BatteryIcon.icon_names:
        target = tmpdir.join(name + ".svg")
        svg_img_as_pypath.copy(target)

    ok = BatteryStatus(
        state=BatteryState.DISCHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as mp:
        mp.setattr(battery, "load_battery", dummy_load_battery(ok))
        batt = BatteryIcon(theme_path=str(tmpdir))

    widget = widget_manager(batt)
    assert widget.eval("len(self.images)") == str(len(BatteryIcon.icon_names))

    widget.eval(
        "from libqtile import images\n"
        "self._test_result = True\n"
        "for img in self.images.values():\n"
        "    if not isinstance(img, images.Img):\n"
        "        self._test_result = False"
    )
    assert widget.eval("self._test_result") == "True"


def test_images_default(widget_manager, monkeypatch):
    """Test BatteryIcon() with the default theme_path

    Ensure that the default images are successfully loaded.
    """
    ok = BatteryStatus(
        state=BatteryState.DISCHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as mp:
        mp.setattr(battery, "load_battery", dummy_load_battery(ok))
        batt = BatteryIcon()

    widget = widget_manager(batt)
    assert widget.eval("len(self.images)") == str(len(BatteryIcon.icon_names))

    widget.eval(
        "from libqtile import images\n"
        "self._test_result = True\n"
        "for img in self.images.values():\n"
        "    if not isinstance(img, images.Img):\n"
        "        self._test_result = False"
    )
    assert widget.eval("self._test_result") == "True"


def test_battery_background(widget_manager, monkeypatch):
    ok = BatteryStatus(
        state=BatteryState.DISCHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    low_background = "ff0000"
    background = "000000"

    with monkeypatch.context() as mp:
        mp.setattr(battery, "load_battery", dummy_load_battery(ok))
        batt = Battery(low_percentage=0.2, low_background=low_background, background=background)

    widget = widget_manager(batt)

    assert widget.eval("self.background") == background
    set_battery_status(widget, "DISCHARGING", 0.1)
    assert widget.eval("self.background") == low_background
    set_battery_status(widget, "DISCHARGING", 0.5)
    assert widget.eval("self.background") == background


def save_battery_percentage(self, charge_start_threshold, charge_end_threshold):
    self._test_thresholds = (charge_start_threshold, charge_end_threshold)


def polled_thresholds(widget):
    """Poll the widget and return any thresholds set during the poll."""
    widget.force_update()
    return widget.eval("getattr(self._battery, '_test_thresholds', None)")


def test_charge_control(widget_manager, monkeypatch):
    monkeypatch.setattr(
        battery._LinuxBattery, "set_battery_charge_thresholds", save_battery_percentage
    )
    batt = Battery(charge_controller=lambda: (5, 10))

    widget = widget_manager(batt)
    assert polled_thresholds(widget) == "(5, 10)"


def test_charge_control_disabled(widget_manager, monkeypatch):
    monkeypatch.setattr(
        battery._LinuxBattery, "set_battery_charge_thresholds", save_battery_percentage
    )
    batt = Battery(charge_controller=None)

    widget = widget_manager(batt)
    assert polled_thresholds(widget) == "None"


def test_charge_control_force_charge(widget_manager, monkeypatch):
    monkeypatch.setattr(
        battery._LinuxBattery, "set_battery_charge_thresholds", save_battery_percentage
    )
    batt = Battery(charge_controller=lambda: (0, 90), force_charge=True)

    widget = widget_manager(batt)
    assert polled_thresholds(widget) == "(0, 100)"


def test_charging_foreground(widget_manager, monkeypatch):
    foreground = "#dddddd"
    charging_foreground = "#00ff00"
    low_foreground = "#ff0000"

    loaded_bat = BatteryStatus(
        state=BatteryState.CHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as mp:
        mp.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(
            foreground=foreground,
            low_foreground=low_foreground,
            charging_foreground=charging_foreground,
            low_percentage=0.3,
        )

    widget = widget_manager(batt)
    wait_for_eval(widget, "self.layout.colour", charging_foreground)


def test_discharging_foreground(widget_manager, monkeypatch):
    foreground = "#dddddd"
    charging_foreground = "#00ff00"
    low_foreground = "#ff0000"

    loaded_bat = BatteryStatus(
        state=BatteryState.DISCHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as mp:
        mp.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(
            foreground=foreground,
            low_foreground=low_foreground,
            charging_foreground=charging_foreground,
            low_percentage=0.3,
        )

    widget = widget_manager(batt)
    wait_for_eval(widget, "self.layout.colour", foreground)


def test_low_foreground(widget_manager, monkeypatch):
    foreground = "#dddddd"
    charging_foreground = "#00ff00"
    low_foreground = "#ff0000"

    loaded_bat = BatteryStatus(
        state=BatteryState.DISCHARGING,
        percent=0.25,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as mp:
        mp.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(
            foreground=foreground,
            low_foreground=low_foreground,
            charging_foreground=charging_foreground,
            low_percentage=0.3,
        )

    widget = widget_manager(batt)
    wait_for_eval(widget, "self.layout.colour", low_foreground)


def test_no_charging_foreground(widget_manager, monkeypatch):
    foreground = "#dddddd"
    charging_foreground = None
    low_foreground = "#ff0000"

    loaded_bat = BatteryStatus(
        state=BatteryState.CHARGING,
        percent=0.5,
        power=15.0,
        time=1729,
        charge_start_threshold=0,
        charge_end_threshold=100,
    )

    with monkeypatch.context() as mp:
        mp.setattr(battery, "load_battery", dummy_load_battery(loaded_bat))
        batt = Battery(
            foreground=foreground,
            low_foreground=low_foreground,
            charging_foreground=charging_foreground,
            low_percentage=0.3,
        )

    widget = widget_manager(batt)
    wait_for_eval(widget, "self.layout.colour", foreground)
