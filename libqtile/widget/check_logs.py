from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from libqtile.bar import Bar
from libqtile.command.base import expose_command
from libqtile.log_utils import get_log_path, logger
from libqtile.widget import base

if TYPE_CHECKING:
    from libqtile.core.manager import Qtile


class CheckLogs(base._TextBox):
    """A widget that tells the user to check the qtile log.

    This widget is automatically inserted into every bar the first time a
    ``WARNING`` (or higher) level message is emitted by qtile. Users do not
    need to add it to their config: it appears on demand so that problems
    surfaced in the log get noticed.

    Clicking the widget dismisses it (removing it from the bar). If another
    warning is emitted later, the widget will reappear.
    """

    defaults = [
        (
            "format",
            "\u26a0 Check qtile log: {path}",
            "Format for the warning message. ``{path}`` is replaced with the log file path.",
        ),
        (
            "no_file_text",
            "\u26a0 Check qtile log output",
            "Text shown when qtile is logging to stdout instead of a file.",
        ),
    ]

    def __init__(self, **config):
        base._TextBox.__init__(self, "", **config)
        self.add_defaults(CheckLogs.defaults)
        self.add_callbacks({"Button1": self.dismiss})

    def _configure(self, qtile: Qtile, bar: Bar) -> None:
        base._TextBox._configure(self, qtile, bar)
        log_path = get_log_path()
        if log_path is None:
            self.text = self.no_file_text
        else:
            self.text = self.format.format(path=str(log_path))

    @expose_command()
    def dismiss(self) -> None:
        """Remove the widget from its bar."""
        if self in self.bar.widgets:
            self.bar.widgets.remove(self)
            self.bar.draw()

    @classmethod
    def inject_into_bars(cls, qtile: Qtile) -> None:
        """Append a ``CheckLogs`` widget to every bar that doesn't already
        have one. Safe to call multiple times."""
        for screen in qtile.screens:
            for side in ("top", "bottom", "left", "right"):
                bar = getattr(screen, side, None)
                if not isinstance(bar, Bar) or not bar._configured:
                    continue
                if any(isinstance(w, cls) for w in bar.widgets):
                    continue

                widget = cls()
                try:
                    widget._configure(qtile, bar)
                    if bar.horizontal:
                        widget.offsety = bar.border_width[0]
                    else:
                        widget.offsetx = bar.border_width[3]
                    bar.widgets.append(widget)
                    qtile.register_widget(widget)
                    bar.draw()
                except Exception:
                    logger.exception("Failed to inject CheckLogs widget")


class _CheckLogsHandler(logging.Handler):
    """Logging handler that schedules a :class:`CheckLogs` widget injection
    whenever a WARNING (or higher) record is emitted.
    """

    def __init__(self, qtile: Qtile, level: int = logging.WARNING) -> None:
        super().__init__(level=level)
        self._qtile = qtile

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        # We need a running event loop to schedule the injection safely,
        # especially since log messages can originate from any thread.
        if getattr(self._qtile, "_eventloop", None) is None:
            return
        try:
            self._qtile.call_soon_threadsafe(CheckLogs.inject_into_bars, self._qtile)
        except Exception:
            # Never let a logging handler raise.
            pass


def install_handler(qtile: Qtile) -> None:
    """Install the :class:`_CheckLogsHandler` so that warnings surface a
    ``CheckLogs`` widget in every bar.

    The handler is only installed when qtile is logging to a real file: in
    tests / Xephyr development we log to stdout and the widget has no
    useful path to point the user at.
    """
    if get_log_path() is None:
        return
    logger.addHandler(_CheckLogsHandler(qtile))
