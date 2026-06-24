import sys
from functools import partial
from importlib import reload
from types import ModuleType

import pytest

import libqtile.config
import libqtile.widget
from libqtile.bar import Bar
from test.conftest import MinimalConf


class Temp:
    def __init__(self, label, temp, fahrenheit=False):
        self.label = label
        self.current = temp
        if fahrenheit:
            self.current = (self.current * 9 / 5) + 32


class MockPsutil(ModuleType):
    @classmethod
    def sensors_temperatures(cls, fahrenheit=False):
        return {"core": [Temp("CPU", 45.0, fahrenheit)], "nvme": [Temp("NVME", 56.3, fahrenheit)]}


def sensors_config(params):
    sys.modules["psutil"] = MockPsutil("psutil")
    from libqtile.widget import sensors

    reload(sensors)

    class SensorsConf(MinimalConf):
        screens = [libqtile.config.Screen(top=Bar([sensors.ThermalSensor(**params)], 10))]

    if "set_defaults" in params:
        SensorsConf.widget_defaults = {"foreground": "123456"}

    return SensorsConf()


@pytest.fixture
def sensors_manager(manager_nospawn, request):
    params = getattr(request, "param", dict())
    manager_nospawn.start(partial(sensors_config, params))
    yield manager_nospawn


def test_thermal_sensor_metric(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].info()["text"] == "45.0°C"


@pytest.mark.parametrize("sensors_manager", [{"metric": False}], indirect=True)
def test_thermal_sensor_imperial(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].info()["text"] == "113.0°F"


@pytest.mark.parametrize("sensors_manager", [{"tag_sensor": "NVME"}], indirect=True)
def test_thermal_sensor_tagged_sensor(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].info()["text"] == "56.3°C"


@pytest.mark.parametrize("sensors_manager", [{"tag_sensor": "does_not_exist"}], indirect=True)
def test_thermal_sensor_unknown_sensor(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].info()["text"] == "N/A"


@pytest.mark.parametrize(
    "sensors_manager", [{"format": "{tag}: {temp:.0f}{unit}"}], indirect=True
)
def test_thermal_sensor_format(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].info()["text"] == "CPU: 45°C"


def test_thermal_sensor_colour_normal(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].eval("self.layout.colour") == "ffffff"


@pytest.mark.parametrize("sensors_manager", [{"threshold": 30}], indirect=True)
def test_thermal_sensor_colour_alert(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].eval("self.layout.colour") == "ff0000"


@pytest.mark.parametrize("sensors_manager", [{"set_defaults": True}], indirect=True)
def test_thermal_sensor_widget_defaults(sensors_manager):
    assert sensors_manager.c.widget["thermalsensor"].eval("self.layout.colour") == "123456"
