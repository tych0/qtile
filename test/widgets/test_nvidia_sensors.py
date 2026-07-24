import pytest

import libqtile.bar
import libqtile.config
from libqtile.widget.nvidia_sensors import NvidiaSensors, _all_sensors_names_correct
from test.helpers import Retry


def test_nvidia_sensors_input_regex():
    correct_sensors = NvidiaSensors(
        format="temp:{temp}°C,fan{fan_speed}asd,performance{perf}fds"
    )._parse_format_string()
    incorrect_sensors = {"tem", "fan_speed", "perf"}
    assert correct_sensors == {"temp", "fan_speed", "perf"}
    assert _all_sensors_names_correct(correct_sensors)
    assert not _all_sensors_names_correct(incorrect_sensors)


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_temperature(widget, temperature):
    assert widget.info()["text"] == temperature


def set_temperature(widget, temperature):
    """Change the mocked nvidia-smi output and repoll the widget."""
    widget.eval(
        f"self.call_process = lambda *args, **kwargs: '{temperature}'\nself.update(self.poll())"
    )


@pytest.fixture
def nvidia_manager(monkeypatch, manager_nospawn, minimal_conf_noscreen):
    widget = NvidiaSensors()
    # Replace internal call_process since we cant rely
    # on the test computer having the required hardware.
    monkeypatch.setattr(widget, "call_process", lambda *args, **kwargs: "20")

    config = minimal_conf_noscreen
    config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([widget], 10))]
    manager_nospawn.start(config)

    yield manager_nospawn.c.widget["nvidiasensors"]


def test_nvidia_sensors_foreground_colour(nvidia_manager):
    # Initial temperature
    wait_for_temperature(nvidia_manager, "20°C")
    assert nvidia_manager.eval("self.layout.colour") == nvidia_manager.eval(
        "self.foreground_normal"
    )

    # Simulate GPU overheating
    set_temperature(nvidia_manager, 90)
    wait_for_temperature(nvidia_manager, "90°C")
    assert nvidia_manager.eval("self.layout.colour") == nvidia_manager.eval(
        "self.foreground_alert"
    )

    # And cooling back down
    set_temperature(nvidia_manager, 20)
    wait_for_temperature(nvidia_manager, "20°C")
    assert nvidia_manager.eval("self.layout.colour") == nvidia_manager.eval(
        "self.foreground_normal"
    )
