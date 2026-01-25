import asyncio
import builtins
import codeop
import contextlib
import io
import re
import time
import traceback
import uuid
from typing import Any

from libqtile.ipc import MessageType
from libqtile.log_utils import logger

ATTR_MATCH = re.compile(r"([\w\.]+?)(?:\.([\w]*))?$")

# Session timeout in seconds (clean up inactive sessions)
SESSION_TIMEOUT = 3600  # 1 hour


def mark_unavailable(func):
    def _wrapper(*args, **kwargs):
        print(f"'{func.__name__}' is disabled in this REPL.")

    return _wrapper


def make_safer_env():
    """
    Returns a dict to be passed to the REPL's global environment.

    Can be used to block harmful commands.
    """

    # Interactive help blocks REPL and will cause qtile to hand
    original_help = builtins.help

    def safe_help(*args):
        """Print help on a specified object."""
        if not args:
            print("Interactive help() is disabled in this REPL.")
        else:
            return original_help(*args)

    # Store original help so we can still call it safely
    builtins.help = safe_help

    # Mask other builtins
    builtins.input = mark_unavailable(builtins.input)

    return {"__builtins__": builtins}


def parse_completion_expr(text):
    """
    Parses an input like 'qtile.win' or 'qtil' and splits it into:
    - object_expr: what to evaluate or look up ('qtile', 'qtil')
    - attr_prefix: what to complete ('', 'win', etc.)
    """
    match = ATTR_MATCH.search(text)
    if not match:
        return None, None
    obj_expr, attr_prefix = match.groups()
    return obj_expr, attr_prefix or ""


def get_completions(text, local_vars):
    expr, attr_prefix = parse_completion_expr(text)

    # Case 1: Completing a top-level variable name
    if "." not in text:
        return [name for name in local_vars if name.startswith(expr)]

    # Case 2: Completing an attribute
    try:
        base = eval(expr, {}, local_vars)
        options = [attr for attr in dir(base) if attr.startswith(attr_prefix)]
        options = [
            f"{expr}.{attr}" + ("(" if callable(getattr(base, attr)) else "") for attr in options
        ]
        options = list(filter(None, options))
        return options
    except Exception:
        return []


class REPLSession:
    """A single REPL session with its own namespace and state."""

    def __init__(self, session_id: str, locals_dict: dict[str, Any]):
        self.session_id = session_id
        self.locals = {**make_safer_env(), **locals_dict}
        self.compiler = codeop.CommandCompiler()
        self.last_active = time.time()

    def evaluate_code(self, code: str) -> str:
        """Evaluate code and return the output."""
        self.last_active = time.time()

        with io.StringIO() as stdout:
            # Capture any stdout and direct to a buffer
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
                try:
                    try:
                        # Try eval (for expressions)
                        expr_code = compile(code, "<stdin>", "eval")
                        result = eval(expr_code, self.locals)
                        if result is not None:
                            # We can use print here as we've redirected stdout
                            print(repr(result))
                    except SyntaxError:
                        # Fallback to exec (for statements)
                        compiled = self.compiler(code)
                        if compiled is not None:
                            exec(compiled, self.locals)
                except Exception:
                    traceback.print_exc()

            return stdout.getvalue()

    def get_completions(self, text: str) -> list[str]:
        """Get completions for the given text."""
        self.last_active = time.time()
        return get_completions(text, self.locals)


class REPLManager:
    """Manages REPL sessions for the IPC server."""

    def __init__(self):
        self.sessions: dict[str, REPLSession] = {}
        self.default_locals: dict[str, Any] = {}
        self.enabled = False
        self.qtile = None

    def enable(self, qtile, locals_dict: dict[str, Any] | None = None) -> None:
        """Enable the REPL functionality."""
        self.qtile = qtile
        self.default_locals = {"qtile": qtile}
        if locals_dict:
            self.default_locals.update(locals_dict)
        self.enabled = True
        logger.info("REPL functionality enabled")

    def disable(self) -> None:
        """Disable REPL functionality and clean up sessions."""
        self.sessions.clear()
        self.enabled = False
        logger.info("REPL functionality disabled")

    def cleanup_inactive_sessions(self) -> None:
        """Remove sessions that have been inactive for too long."""
        now = time.time()
        expired = [
            sid
            for sid, session in self.sessions.items()
            if now - session.last_active > SESSION_TIMEOUT
        ]
        for sid in expired:
            del self.sessions[sid]
            logger.debug("Cleaned up inactive REPL session: %s", sid)

    def get_or_create_session(self, session_id: str | None = None) -> REPLSession:
        """Get an existing session or create a new one."""
        self.cleanup_inactive_sessions()

        if session_id and session_id in self.sessions:
            return self.sessions[session_id]

        # Create new session
        new_id = session_id or str(uuid.uuid4())
        session = REPLSession(new_id, self.default_locals)
        self.sessions[new_id] = session
        logger.debug("Created new REPL session: %s", new_id)
        return session

    def remove_session(self, session_id: str) -> None:
        """Remove a specific session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.debug("Removed REPL session: %s", session_id)

    async def handle_message(
        self, msg_type: MessageType, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle REPL-related messages from the IPC server."""
        if not self.enabled:
            return {"error": "REPL not enabled. Run start_repl_server first."}

        # Check if session is locked
        if self.qtile is not None and self.qtile.locked:
            return {"error": "Session is locked."}

        if msg_type == MessageType.REPL_SESSION_START:
            session = self.get_or_create_session()
            return {
                "session_id": session.session_id,
                "message": "REPL session started. Press Ctrl+C to exit.",
            }

        if msg_type == MessageType.REPL_SESSION_END:
            session_id = payload.get("session_id")
            if session_id:
                self.remove_session(session_id)
            return {"success": True}

        if msg_type == MessageType.REPL_EVAL:
            code = payload.get("code", "")
            session_id = payload.get("session_id")
            session = self.get_or_create_session(session_id)

            # Evaluate code in a thread so blocking calls don't block the eventloop
            loop = asyncio.get_running_loop()
            output = await loop.run_in_executor(None, session.evaluate_code, code)

            return {
                "session_id": session.session_id,
                "output": output.strip(),
            }

        if msg_type == MessageType.REPL_COMPLETE:
            text = payload.get("text", "")
            session_id = payload.get("session_id")
            session = self.get_or_create_session(session_id)

            completions = session.get_completions(text)

            return {
                "session_id": session.session_id,
                "completions": completions,
            }

        return {"error": f"Unknown REPL message type: {msg_type}"}


# Global REPL manager instance
repl_manager = REPLManager()
