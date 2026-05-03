"""Backend-agnostic unit tests for Window.activate() and activate_by_config().

These exercise the logic in libqtile/backend/base/window.py directly without
requiring an X11 or Wayland backend. They lock in the behavior that fixed
issue #5821: a window whose group is already visible on another screen must
be focused by moving focus to that screen, not by swapping groups between
screens.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from libqtile.backend.base.window import Window


def _make_self(*, group_screen, current_screen, focus_behavior="focus", group=None):
    """Build a mock `self` for invoking unbound Window methods."""
    qtile = MagicMock()
    qtile.current_screen = current_screen
    qtile.config = SimpleNamespace(focus_on_window_activation=focus_behavior)
    if group is None:
        group = MagicMock()
    group.screen = group_screen
    if group_screen is not None:
        group_screen.index = getattr(group_screen, "index", 1)

    return MagicMock(qtile=qtile, group=group, urgent=False)


def test_activate_same_screen_uses_set_group():
    screen = MagicMock(index=0)
    obj = _make_self(group_screen=screen, current_screen=screen)

    result = Window.activate(obj)

    assert result is True
    obj.qtile.current_screen.set_group.assert_called_once_with(obj.group)
    obj.qtile.focus_screen.assert_not_called()
    obj.group.focus.assert_called_once_with(obj)
    obj.bring_to_front.assert_called_once()


def test_activate_other_visible_screen_focuses_screen():
    """Issue #5821: don't swap groups when the window's group is visible
    on a different screen — just move focus to that screen."""
    current = MagicMock(index=0)
    other = MagicMock(index=1)
    obj = _make_self(group_screen=other, current_screen=current)

    result = Window.activate(obj)

    assert result is True
    obj.qtile.focus_screen.assert_called_once_with(1, warp=False)
    obj.qtile.current_screen.set_group.assert_not_called()
    obj.group.focus.assert_called_once_with(obj)


def test_activate_hidden_group_pulls_to_current_screen():
    current = MagicMock(index=0)
    obj = _make_self(group_screen=None, current_screen=current)

    result = Window.activate(obj)

    assert result is True
    obj.qtile.current_screen.set_group.assert_called_once_with(obj.group)
    obj.qtile.focus_screen.assert_not_called()


def test_activate_returns_false_for_unmanaged():
    obj = MagicMock()
    obj.group = None

    assert Window.activate(obj) is False


def test_activate_by_config_focus_calls_activate():
    obj = _make_self(group_screen=None, current_screen=MagicMock(), focus_behavior="focus")

    Window.activate_by_config(obj)

    obj.activate.assert_called_once()


def test_activate_by_config_smart_visible_other_screen_focuses():
    """The new "smart" semantics: focus when the group is visible on any
    screen (not just current) — don't mark urgent."""
    other = MagicMock(index=1)
    obj = _make_self(
        group_screen=other,
        current_screen=MagicMock(index=0),
        focus_behavior="smart",
    )

    with patch("libqtile.backend.base.window.hook") as mock_hook:
        Window.activate_by_config(obj)

    obj.activate.assert_called_once()
    mock_hook.fire.assert_not_called()
    assert obj.urgent is False


def test_activate_by_config_smart_hidden_group_marks_urgent():
    obj = _make_self(
        group_screen=None,
        current_screen=MagicMock(index=0),
        focus_behavior="smart",
    )

    with patch("libqtile.backend.base.window.hook") as mock_hook:
        Window.activate_by_config(obj)

    obj.activate.assert_not_called()
    assert obj.urgent is True
    mock_hook.fire.assert_called_once_with("client_urgent_hint_changed", obj)


def test_activate_by_config_urgent_marks_urgent():
    obj = _make_self(
        group_screen=MagicMock(index=1),
        current_screen=MagicMock(index=0),
        focus_behavior="urgent",
    )

    with patch("libqtile.backend.base.window.hook") as mock_hook:
        Window.activate_by_config(obj)

    obj.activate.assert_not_called()
    assert obj.urgent is True
    mock_hook.fire.assert_called_once_with("client_urgent_hint_changed", obj)


def test_activate_by_config_never_does_nothing():
    obj = _make_self(
        group_screen=MagicMock(index=1),
        current_screen=MagicMock(index=0),
        focus_behavior="never",
    )

    with patch("libqtile.backend.base.window.hook") as mock_hook:
        Window.activate_by_config(obj)

    obj.activate.assert_not_called()
    mock_hook.fire.assert_not_called()
    assert obj.urgent is False


def test_activate_by_config_callable_returning_true_focuses():
    obj = _make_self(
        group_screen=None,
        current_screen=MagicMock(index=0),
        focus_behavior=lambda w: True,
    )

    Window.activate_by_config(obj)

    obj.activate.assert_called_once()
