from __future__ import annotations

import asyncio
import contextlib
import typing
from abc import ABCMeta, abstractmethod
from typing import Any

from libqtile import config, hook
from libqtile.backend.base.idle_inhibit import IdleInhibitorManager
from libqtile.backend.base.idle_notify import IdleNotifier
from libqtile.command.base import CommandObject, ItemT, expose_command
from libqtile.config import Screen
from libqtile.group import _Group

if typing.TYPE_CHECKING:
    from libqtile.backend.base import Internal
    from libqtile.core.manager import Qtile


class Core(CommandObject, metaclass=ABCMeta):
    painter: Any
    supports_restarting: bool = True
    qtile: Qtile
    idle_inhibitor_manager: IdleInhibitorManager[Any]
    idle_notifier: IdleNotifier

    # Screen change events often arrive in bursts, e.g. as an xrandr call or a
    # wlr-output-management transaction applies each output's settings in
    # turn. An isolated event fires the screen_change hook immediately, but
    # events following within this window (in seconds) are coalesced into a
    # single fire once they have settled, so that we don't reconfigure screens
    # for every intermediate state.
    screen_change_debounce: float = 0.15
    _screen_change_timer: asyncio.TimerHandle | None = None
    _screen_change_pending: bool = False
    _screen_change_event: Any = None

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the backend"""

    def _items(self, name: str) -> ItemT:
        return None

    def _select(self, name, sel):
        return None

    @abstractmethod
    def finalize(self):
        """Destructor/Clean up resources"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    @abstractmethod
    def setup_listener(self) -> None:
        """Setup a listener for the given qtile instance"""

    @abstractmethod
    def remove_listener(self) -> None:
        """Setup a listener for the given qtile instance"""

    def update_desktops(self, groups: list[_Group], index: int) -> None:
        """Set the current desktops of the window manager"""

    def fire_screen_change(self, event: Any = None) -> None:
        """
        Fire the screen_change hook, debounced.

        Backends should route screen change events through this instead of
        firing the hook directly. An isolated event fires the hook
        immediately; events following within screen_change_debounce seconds
        of the previous one are coalesced into a single fire, with the most
        recent event, once they have settled.
        """
        self._screen_change_event = event
        try:
            eventloop = asyncio.get_running_loop()
        except RuntimeError:
            # There is no event loop yet (we are still starting up), so we
            # cannot defer the hook; fire it directly.
            self._flush_screen_change()
            return
        if self._screen_change_timer is None:
            # Leading edge: fire immediately, so that isolated events (e.g. a
            # monitor being plugged in) are handled without delay; the timer
            # below coalesces any events that follow.
            self._flush_screen_change()
        else:
            self._screen_change_pending = True
            self._screen_change_timer.cancel()
        self._screen_change_timer = eventloop.call_later(
            self.screen_change_debounce, self._screen_change_settled
        )

    def _screen_change_settled(self) -> None:
        self._screen_change_timer = None
        if self._screen_change_pending:
            self._flush_screen_change()

    def _flush_screen_change(self) -> None:
        self._screen_change_pending = False
        event, self._screen_change_event = self._screen_change_event, None
        hook.fire("screen_change", event)

    def _cancel_screen_change(self) -> None:
        """Drop any pending debounced screen_change hook; call on finalize."""
        if self._screen_change_timer is not None:
            self._screen_change_timer.cancel()
            self._screen_change_timer = None
        self._screen_change_pending = False
        self._screen_change_event = None

    @abstractmethod
    def get_output_info(self) -> list[config.Output]:
        """Get the output information"""

    @abstractmethod
    def grab_key(self, key: config.Key | config.KeyChord) -> tuple[int, int]:
        """Configure the backend to grab the key event"""

    @abstractmethod
    def ungrab_key(self, key: config.Key | config.KeyChord) -> tuple[int, int]:
        """Release the given key event"""

    @abstractmethod
    def ungrab_keys(self) -> None:
        """Release the grabbed key events"""

    @abstractmethod
    def grab_button(self, mouse: config.Mouse) -> int:
        """Configure the backend to grab the mouse event"""

    def ungrab_buttons(self) -> None:
        """Release the grabbed button events"""

    def grab_pointer(self) -> None:
        """Configure the backend to grab mouse events"""

    def ungrab_pointer(self) -> None:
        """Release grabbed pointer events"""

    def on_config_load(self, initial: bool) -> None:
        """
        Respond to config loading. `initial` will be `True` if Qtile just started.
        """

    def warp_pointer(self, x: int, y: int) -> None:
        """Warp the pointer to the given coordinates relative."""

    @contextlib.contextmanager
    def masked(self):
        """A context manager to suppress window events while operating on many windows."""
        yield

    def create_internal(
        self, x: int, y: int, width: int, height: int, depth: int = 32
    ) -> Internal:
        """Create an internal window controlled by Qtile."""
        raise NotImplementedError  # Only error when called, not when instantiating class

    def flush(self) -> None:
        """If needed, flush the backend's event queue."""

    def simulate_keypress(self, modifiers: list[str], key: str) -> None:
        """Simulate a keypress with given modifiers"""

    def keysym_from_name(self, name: str) -> int:
        """Get the keysym for a key from its name"""
        raise NotImplementedError

    def get_mouse_position(self) -> tuple[int, int]:
        """Get mouse coordinates."""
        raise NotImplementedError

    @expose_command()
    def info(self) -> dict[str, Any]:
        """Get basic information about the running backend."""
        return {"backend": self.name, "display_name": self.display_name}

    def check_screen_fullscreen_background(self, screen: Screen | None = None) -> None:
        """Toggles fullscreen background if any window on the screen is fullscreen."""
        # Wayland only

    def update_backend_log_level(self) -> None:
        """Update the backend log level based on Qtile's log level."""
        # Wayland only

    @property
    def inhibited(self) -> bool:
        if not hasattr(self, "_inhibited"):
            self._inhibited = False

        return self._inhibited

    @inhibited.setter
    def inhibited(self, value: bool):
        if value != self.inhibited:
            self._inhibited = value
            hook.fire("idle_inhibitor_change", value)

    @expose_command()
    def set_idle_inhibitor(self) -> None:
        """Create a global idle inhibitor."""
        self.idle_inhibitor_manager.add_global_inhibitor()

    @expose_command()
    def remove_idle_inhibitor(self) -> None:
        """Remove global idle inhibitor."""
        self.idle_inhibitor_manager.remove_global_inhibitor()

    @expose_command()
    def get_idle_inhibitors(self, active_only: bool = False) -> list[str]:
        """Return list of inhibitors."""
        return [
            f"{inhibitor!r}"
            for inhibitor in self.idle_inhibitor_manager.inhibitors
            if not active_only or (active_only and inhibitor.check())
        ]
