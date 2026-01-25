import pytest

from libqtile.interactive.repl import (
    REPLManager,
    REPLSession,
    get_completions,
)
from libqtile.ipc import MessageType


def test_get_completions_top_level():
    local_vars = {"qtile": "dummy", "qtiles": 123}
    result = get_completions("qti", local_vars)
    assert "qtile" in result
    assert "qtiles" in result


def test_get_completions_attribute():
    class Dummy:
        def method(self):
            pass

        val = 42

    local_vars = {"dummy": Dummy()}
    result = get_completions("dummy.me", local_vars)
    assert "dummy.method(" in result

    result = get_completions("dummy.va", local_vars)
    assert "dummy.val" in result


def test_get_completions_invalid_expr():
    result = get_completions("invalid..expr", {})
    assert result == []


def test_repl_session_evaluate_expression():
    """Test that REPLSession can evaluate expressions."""
    session = REPLSession("test-session", {"x": 123})
    result = session.evaluate_code("x")
    assert "123" in result


def test_repl_session_evaluate_statement():
    """Test that REPLSession can execute statements."""
    session = REPLSession("test-session", {})
    session.evaluate_code("y = 456")
    result = session.evaluate_code("y")
    assert "456" in result


def test_repl_session_completions():
    """Test that REPLSession provides completions."""
    session = REPLSession("test-session", {"qtile": "dummy", "qtiles": 123})
    result = session.get_completions("qti")
    assert "qtile" in result
    assert "qtiles" in result


def test_repl_manager_enable_disable():
    """Test REPLManager enable/disable."""
    manager = REPLManager()
    assert not manager.enabled

    # Mock qtile object
    class MockQtile:
        locked = False

    manager.enable(MockQtile())
    assert manager.enabled
    assert "qtile" in manager.default_locals

    manager.disable()
    assert not manager.enabled
    assert len(manager.sessions) == 0


def test_repl_manager_session_lifecycle():
    """Test REPLManager session creation and removal."""
    manager = REPLManager()

    class MockQtile:
        locked = False

    manager.enable(MockQtile())

    # Create a session
    session = manager.get_or_create_session()
    assert session.session_id in manager.sessions

    # Get the same session back
    same_session = manager.get_or_create_session(session.session_id)
    assert same_session is session

    # Remove the session
    manager.remove_session(session.session_id)
    assert session.session_id not in manager.sessions


@pytest.mark.anyio
async def test_repl_manager_handle_eval():
    """Test REPLManager handles REPL_EVAL messages."""
    manager = REPLManager()

    class MockQtile:
        locked = False

    manager.enable(MockQtile(), {"x": 123})

    response = await manager.handle_message(MessageType.REPL_EVAL, {"code": "x"})
    assert "output" in response
    assert "123" in response["output"]
    assert "session_id" in response


@pytest.mark.anyio
async def test_repl_manager_handle_complete():
    """Test REPLManager handles REPL_COMPLETE messages."""
    manager = REPLManager()

    class MockQtile:
        locked = False

    manager.enable(MockQtile(), {"qtile": "dummy"})

    response = await manager.handle_message(MessageType.REPL_COMPLETE, {"text": "qti"})
    assert "completions" in response
    assert "qtile" in response["completions"]


@pytest.mark.anyio
async def test_repl_manager_handle_session_start():
    """Test REPLManager handles REPL_SESSION_START messages."""
    manager = REPLManager()

    class MockQtile:
        locked = False

    manager.enable(MockQtile())

    response = await manager.handle_message(MessageType.REPL_SESSION_START, {})
    assert "session_id" in response
    assert response["session_id"] in manager.sessions


@pytest.mark.anyio
async def test_repl_manager_not_enabled():
    """Test REPLManager returns error when not enabled."""
    manager = REPLManager()

    response = await manager.handle_message(MessageType.REPL_EVAL, {"code": "1+1"})
    assert "error" in response
    assert "not enabled" in response["error"]
