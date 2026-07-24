import pytest

from libqtile.widget.nvidia_sensors import NvidiaSensors, _all_sensors_names_correct
from test.widgets.conftest import wait_for_eval, wait_for_text

FOREGROUND_NORMAL = "#ffffff"
FOREGROUND_ALERT = "#ff0000"


def test_nvidia_sensors_input_regex():
    correct_sensors = NvidiaSensors(
        format="temp:{temp}°C,fan{fan_speed}asd,performance{perf}fds"
    )._parse_format_string()
    incorrect_sensors = {"tem", "fan_speed", "perf"}
    assert correct_sensors == {"temp", "fan_speed", "perf"}
    assert _all_sensors_names_correct(correct_sensors)
    assert not _all_sensors_names_correct(incorrect_sensors)


def set_temperature(widget, temperature):
    """Change the mocked nvidia-smi output and repoll the widget."""
    widget.eval(f"self.call_process = lambda *args, **kwargs: '{temperature}'")
    widget.force_update()


@pytest.fixture
def nvidia_widget(monkeypatch, widget_manager):
    widget = NvidiaSensors(foreground=FOREGROUND_NORMAL, foreground_alert=FOREGROUND_ALERT)
    # Replace internal call_process since we cant rely
    # on the test computer having the required hardware.
    monkeypatch.setattr(widget, "call_process", lambda *args, **kwargs: "20")

    yield widget_manager(widget)


def test_nvidia_sensors_foreground_colour(nvidia_widget):
    # Initial temperature
    wait_for_text(nvidia_widget, "20°C")
    wait_for_eval(nvidia_widget, "self.layout.colour", FOREGROUND_NORMAL)

    # Simulate GPU overheating
    set_temperature(nvidia_widget, 90)
    wait_for_text(nvidia_widget, "90°C")
    wait_for_eval(nvidia_widget, "self.layout.colour", FOREGROUND_ALERT)

    # And cooling back down
    set_temperature(nvidia_widget, 20)
    wait_for_text(nvidia_widget, "20°C")
    wait_for_eval(nvidia_widget, "self.layout.colour", FOREGROUND_NORMAL)
