import pytest

from libqtile.backend import detect_backend, get_core
from libqtile.utils import QtileError


def test_get_core_bad():
    with pytest.raises(QtileError):
        get_core("NonBackend").finalize()


@pytest.mark.parametrize(
    "env,expected",
    [
        # XDG_SESSION_TYPE wins when it names a known backend.
        ({"XDG_SESSION_TYPE": "wayland"}, "wayland"),
        ({"XDG_SESSION_TYPE": "x11"}, "x11"),
        # ... and beats the display-variable fallbacks.
        ({"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0"}, "x11"),
        # Unknown/unset session type falls back to the present display.
        ({"XDG_SESSION_TYPE": "tty", "WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        ({"DISPLAY": ":0"}, "x11"),
        ({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}, "wayland"),
        # Nothing to go on: default to x11.
        ({}, "x11"),
    ],
)
def test_detect_backend(monkeypatch, env, expected):
    for var in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    assert detect_backend() == expected
