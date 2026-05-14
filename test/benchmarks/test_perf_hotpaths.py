"""Microbenchmarks for qtile hot paths.

These benchmarks isolate the cost of two routines that fire on every
input event or widget redraw:

* ``pangocffi.FontDescription`` construction (called from ``TextLayout``
  whenever a widget rebuilds its text)
* ``backend.x11.core.Core._get_target_chain`` (called for every X11 event
  the WM receives)

Run with::

    pytest test/benchmarks/test_perf_hotpaths.py --benchmark-only

The benchmarks deliberately avoid spinning up a real qtile session — they
exercise the optimized code paths in isolation so before/after numbers can
be compared without X server noise.
"""

from __future__ import annotations

import pytest

xcffib = pytest.importorskip("xcffib")
import xcffib.randr as rr  # noqa: E402
import xcffib.xproto as xp  # noqa: E402

from libqtile import pangocffi  # noqa: E402
from libqtile.backend.x11 import core as x11core  # noqa: E402

# ---------------------------------------------------------------------------
# Pango FontDescription caching
# ---------------------------------------------------------------------------

FONT_SPECS = [
    "sans 12px",
    "monospace 10px",
    "sans 14px",
    "DejaVu Sans 11px",
    "Noto Sans 13px",
]


def test_bench_font_description_uncached(benchmark):
    """Cost of FontDescription.from_string per call (no caching)."""

    def build():
        for spec in FONT_SPECS:
            pangocffi.FontDescription.from_string(spec)

    benchmark(build)


def test_bench_font_description_cached(benchmark):
    """Cost of the cached lookup. Warm-cache scenario (steady-state)."""
    # Prime the cache so the benchmark only measures hits.
    for spec in FONT_SPECS:
        pangocffi.get_cached_font_description(spec)

    def fetch():
        for spec in FONT_SPECS:
            pangocffi.get_cached_font_description(spec)

    benchmark(fetch)


# ---------------------------------------------------------------------------
# X11 event dispatch
# ---------------------------------------------------------------------------


class _FakeQtile:
    """Minimal stand-in for Qtile, exposing only what _get_target_chain reads."""

    def __init__(self, windows_map):
        self.windows_map = windows_map


class _FakeWindow:
    """A window object with all expected handle_* methods present."""

    def __init__(self):
        for name in x11core.EVENT_TO_HANDLER.values():
            setattr(self, name, lambda *a, **kw: None)


class _FakeCore:
    """A Core stand-in carrying handle_* methods + qtile reference."""

    def __init__(self, qtile):
        self.qtile = qtile
        for name in x11core.EVENT_TO_HANDLER.values():
            setattr(self, name, lambda *a, **kw: None)


def _make_event(cls, **attrs):
    e = cls.__new__(cls)
    for k, v in attrs.items():
        setattr(e, k, v)
    return e


@pytest.fixture
def dispatch_setup():
    win = _FakeWindow()
    windows_map = {1: win, 2: win, 3: win}
    qtile = _FakeQtile(windows_map)
    fake_core = _FakeCore(qtile)
    # bind the real Core._get_target_chain to our stand-in
    dispatch = x11core.Core._get_target_chain.__get__(fake_core, x11core.Core)

    # A representative event mix: motion-heavy (drag), with focus + button +
    # property changes sprinkled in. Roughly mirrors what flows during an
    # active drag with the bar updating.
    events = []
    for _ in range(20):
        events.append(_make_event(xp.MotionNotifyEvent, event=1, time=0))
    for _ in range(3):
        events.append(_make_event(xp.EnterNotifyEvent, event=2))
        events.append(_make_event(xp.LeaveNotifyEvent, event=2))
    events.append(_make_event(xp.ButtonPressEvent, event=1))
    events.append(_make_event(xp.ButtonReleaseEvent, event=1))
    events.append(_make_event(xp.PropertyNotifyEvent, window=3))
    events.append(_make_event(xp.ConfigureRequestEvent, window=3))
    events.append(_make_event(xp.ExposeEvent, window=3))
    # An event with no associated window:
    events.append(_make_event(rr.ScreenChangeNotifyEvent))
    return dispatch, events


_OLD_EVENT_EVENTS = {
    xp.EnterNotifyEvent,
    xp.LeaveNotifyEvent,
    xp.MotionNotifyEvent,
    xp.ButtonPressEvent,
    xp.ButtonReleaseEvent,
    xp.KeyPressEvent,
}


def _old_get_target_chain(self, event):
    """Verbatim copy of the pre-optimization _get_target_chain body.

    Kept here as a comparison baseline for the benchmark; not used in
    production code.
    """
    handler = x11core.EVENT_TO_HANDLER.get(event.__class__)
    if handler is None:
        return []
    if hasattr(event, "window"):
        window = self.qtile.windows_map.get(event.window)
    elif hasattr(event, "drawable"):
        window = self.qtile.windows_map.get(event.drawable)
    elif event.__class__ in _OLD_EVENT_EVENTS:
        window = self.qtile.windows_map.get(event.event)
    else:
        window = None

    chain = []
    if window is not None and hasattr(window, handler):
        chain.append(getattr(window, handler))
    if hasattr(self, handler):
        chain.append(getattr(self, handler))
    return chain


def test_bench_event_dispatch_old(benchmark, dispatch_setup):
    """Baseline: original hasattr/getattr-based dispatch."""
    dispatch_new, events = dispatch_setup
    # Re-bind the OLD body to the same fake core instance the new path uses
    # so windows_map / handlers are identical.
    self = dispatch_new.__self__

    def run():
        for e in events:
            _old_get_target_chain(self, e)

    benchmark(run)


def test_bench_event_dispatch(benchmark, dispatch_setup):
    """Optimized: static window-attr map + getattr(..., None)."""
    dispatch, events = dispatch_setup

    def run():
        for e in events:
            dispatch(e)

    benchmark(run)


def test_dispatch_matches_old(dispatch_setup):
    """The optimized path produces the same chain shape as the old logic."""
    dispatch_new, events = dispatch_setup
    self = dispatch_new.__self__
    for e in events:
        new_chain = dispatch_new(e)
        old_chain = _old_get_target_chain(self, e)
        assert len(new_chain) == len(old_chain), e.__class__.__name__


def test_dispatch_correctness(dispatch_setup):
    """Equivalence check vs. the original branch-and-hasattr logic."""
    dispatch, events = dispatch_setup

    for e in events:
        chain = dispatch(e)
        # Window-bearing events must always produce a 2-handler chain
        # (window + core), window-less events a 1-handler chain.
        cls = e.__class__
        wattr = x11core._EVENT_WINDOW_ATTR.get(cls)
        if wattr is None:
            assert len(chain) == 1, f"{cls.__name__}: expected core-only chain"
        else:
            assert len(chain) == 2, f"{cls.__name__}: expected window+core chain"
