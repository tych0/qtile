from __future__ import annotations

import importlib
import importlib.util
import os
from typing import TYPE_CHECKING, Any

from libqtile.utils import QtileError

if TYPE_CHECKING:
    from libqtile.backend.base import Core


CORES = {
    "wayland": (),
    "x11": ("xcffib",),
}


def detect_backend() -> str:
    """Guess which backend to use from the environment.

    Used when no backend is given explicitly. The session type set by logind /
    the display manager takes precedence, falling back to the presence of a
    Wayland or X11 display (e.g. a bare TTY or a nested session), and finally to
    x11.
    """
    session_type = os.environ.get("XDG_SESSION_TYPE")
    if session_type in CORES:
        return session_type
    if "WAYLAND_DISPLAY" in os.environ:
        return "wayland"
    if "DISPLAY" in os.environ:
        return "x11"
    return "x11"


def has_deps(backend: str) -> list[str]:
    """
    Check if the backend has all its dependencies installed.

    Args:
        backend: The backend to check.

    Returns:
        A list of missing dependencies. If this is empty, we can use this backend.
    """
    if backend not in CORES:
        raise QtileError(f"Backend {backend} does not exist")

    not_found = []
    for dep in CORES[backend]:
        if not importlib.util.find_spec(dep):
            not_found.append(dep)

    return not_found


def get_core(backend: str, *args: Any) -> Core:
    if backend not in CORES:
        raise QtileError(f"Backend {backend} does not exist")

    return importlib.import_module(f"libqtile.backend.{backend}.core").Core(*args)
