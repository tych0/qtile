"""
Lint test that catches ``hook.subscribe.X`` calls in widget/bar modules that
have no matching ``hook.unsubscribe.X`` in the same module.

Leaving a subscription in place after a widget or bar is finalized keeps the
finalized object reachable from the global hook registry, which prevents it
(and the cairo/X11 resources it owns) from being garbage collected. This
shows up as growing memory on screen reconfigure and config reload.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LIBQTILE = REPO_ROOT / "libqtile"

# Files where the imbalance is intentional (e.g. one-shot, transient, or
# explicitly tracked elsewhere). Keep this list short — prefer fixing.
ALLOW_LIST: set[str] = set()


def _modules_to_check() -> list[pathlib.Path]:
    paths = list((LIBQTILE / "widget").rglob("*.py"))
    paths.append(LIBQTILE / "bar.py")
    return paths


def _attr_chain(node: ast.AST) -> list[str] | None:
    """Return the dotted attribute chain for ``hook.subscribe.X`` style refs."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def _collect_hook_events(tree: ast.AST, kind: str) -> set[str]:
    """Collect the set of event names referenced as ``hook.<kind>.<event>(...)``."""
    events: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _attr_chain(node.func)
        if chain is None or len(chain) < 3:
            continue
        if chain[-3] == "hook" and chain[-2] == kind:
            events.add(chain[-1])
    return events


@pytest.mark.parametrize("path", _modules_to_check(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_hook_subscribe_has_unsubscribe(path: pathlib.Path) -> None:
    rel = str(path.relative_to(REPO_ROOT))
    if rel in ALLOW_LIST:
        pytest.skip(f"{rel} in ALLOW_LIST")

    tree = ast.parse(path.read_text())
    subscribed = _collect_hook_events(tree, "subscribe")
    unsubscribed = _collect_hook_events(tree, "unsubscribe")

    missing = subscribed - unsubscribed
    assert not missing, (
        f"{rel}: hook.subscribe.* events without a matching hook.unsubscribe.* "
        f"in the same module: {sorted(missing)}. "
        f"Add the matching hook.unsubscribe call(s) in finalize() so the widget/bar "
        f"can be garbage collected on reload/screen-reconfigure."
    )
