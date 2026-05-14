"""Synthetic profiling harness for qtile drawer hot paths.

Runs a widget-redraw-like workload against an offscreen cairo RecordingSurface
and prints a cProfile summary so we can spot any remaining easy wins.

The Drawer's `_draw` is a no-op in the base class — subclasses (XCB/Wayland)
push to a real backend surface — so the harness exercises everything *up to*
the backend handoff: color parsing, font/text layout, cairo path ops.

Usage::

    /tmp/qvenv/bin/python tools/profile_drawer.py [N]
"""

from __future__ import annotations

import cProfile
import pstats
import sys
import types

from libqtile.backend.base import drawer as drawer_mod


def make_drawer(width=1920, height=30):
    # Drawer.__init__ only touches self._win.{nothing} — the win argument is
    # stashed for later backend-specific use and isn't needed for the
    # base-class draw path.
    win = types.SimpleNamespace()
    d = drawer_mod.Drawer(win, width, height)
    return d


def widget_redraw_once(d, layout):
    """Simulate one widget tick: clear, draw text, draw separator rect."""
    d.clear("#222222ff")
    layout.text = f"CPU 42% | MEM 7.1 GiB | {hash(object()) & 0xFFFF}"
    layout.draw(10, 5)
    d.fillrect(200, 0, 2, d.height, 1)
    d.rectangle(220, 4, 60, 22, 1)
    # Force the recorded ops to flush; mirrors the per-frame reset.
    d._reset_surface()


def run(n):
    d = make_drawer()
    layout = d.textlayout(
        "hello world",
        "#ffffffff",
        "sans",
        12,
        None,
        markup=False,
    )

    for _ in range(50):
        widget_redraw_once(d, layout)

    pr = cProfile.Profile()
    pr.enable()
    for _ in range(n):
        widget_redraw_once(d, layout)
    pr.disable()

    stats = pstats.Stats(pr).strip_dirs().sort_stats("cumulative")
    print(f"\n== cumulative time, top 25 ({n} iterations) ==")
    stats.print_stats(25)

    stats.sort_stats("tottime")
    print("\n== self (tottime) time, top 25 ==")
    stats.print_stats(25)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    run(n)
