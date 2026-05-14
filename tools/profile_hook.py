"""Profile hook.fire dispatch with N subscribers."""

from __future__ import annotations

import cProfile
import pstats
import sys

import libqtile.backend.base.window  # noqa: F401 - ensure attr is resolved at fire time
from libqtile import hook


def setup(n_subs=10):
    # use unique registry name to avoid collision with the default one
    # that hook.py constructs at import time.
    name = f"profile-{id(object())}"
    reg = hook.Registry(name, [hook.Hook("client_focus", "")])
    # subscriptions table is global in hook module
    hook.subscriptions.clear()
    handlers = []
    for i in range(n_subs):

        def h(*args, **kwargs):
            return None

        h.__name__ = f"h{i}"
        handlers.append(h)
        getattr(reg.subscribe, "client_focus")(h)
    return reg


def run(n_fires, n_subs):
    reg = setup(n_subs)

    class FakeWin:
        pass

    win = FakeWin()

    # warmup
    for _ in range(50):
        reg.fire("client_focus", win)

    pr = cProfile.Profile()
    pr.enable()
    for _ in range(n_fires):
        reg.fire("client_focus", win)
    pr.disable()

    stats = pstats.Stats(pr).strip_dirs().sort_stats("cumulative")
    print(f"\n== cumulative, top 20 ({n_fires} fires x {n_subs} subs) ==")
    stats.print_stats(20)
    stats.sort_stats("tottime")
    print("\n== tottime, top 20 ==")
    stats.print_stats(20)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    subs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    run(n, subs)
