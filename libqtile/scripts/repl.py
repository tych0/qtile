from __future__ import annotations

import asyncio
import codeop
import re
import sys
from typing import TYPE_CHECKING

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.patch_stdout import patch_stdout

    HAS_PT = True
except (ImportError, ModuleNotFoundError):
    HAS_PT = False

from libqtile.ipc import PersistentClient, find_sockfile
from libqtile.scripts.cmd_obj import cmd_obj

if TYPE_CHECKING:
    pass


class Command:
    """Wrapper to call commands via command interface."""

    def __init__(self, command, obj_spec=["root"], *args, **kwargs):
        self.function = command
        self.socket = None
        self.args = args
        self.kwargs = kwargs
        self.obj_spec = obj_spec
        self.info = False

    def __call__(self):
        return cmd_obj(self)


# Calls to start and stop the qtile REPL server
# Sends commands via qtile cmd-obj
start_server = Command("start_repl_server")
stop_server = Command("stop_repl_server")


def is_code_complete(text: str) -> bool:
    """Method to verify that we have a valid code block."""
    try:
        code_obj = codeop.compile_command(text, symbol="exec")

        # Incomplete (e.g. after 'def foo():')
        if code_obj is None:
            return False

        # Only treat as complete if there's a double blank line at the end for compound blocks
        lines = text.rstrip("\n").splitlines()
        return len(lines) <= 1 or text.endswith("\n\n")
    except (SyntaxError, OverflowError, ValueError, TypeError):
        return True


async def repl_session(socket_path: str) -> None:
    """Run the REPL session using the new IPC protocol."""
    async with PersistentClient(socket_path) as client:
        # Start a REPL session
        response = await client.start_repl_session()
        session_id = response
        print("Connected to Qtile REPL\nPress Ctrl+C to exit.\n")

        class IPCCompleter(Completer):
            def __init__(self, client: PersistentClient, session_id: str):
                self.client = client
                self.session_id = session_id
                self._loop = asyncio.get_event_loop()

            def get_completions(self, document, _complete_event):
                text_before_cursor = document.text_before_cursor

                # Extract the current word or attribute expression (e.g., qtile.cur)
                match = re.search(r"([\w\.]+)$", text_before_cursor)
                if not match:
                    return

                word = match.group(1)
                start_position = -len(word)

                # Get completions from server
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.client.send_repl_complete(word, self.session_id),
                        self._loop,
                    )
                    completions = future.result(timeout=5)
                except Exception:
                    return

                for opt in completions:
                    yield Completion(opt, start_position=start_position)

        kb = KeyBindings()
        completer = IPCCompleter(client, session_id)

        # Create a session instance
        session = PromptSession(
            completer=completer,
            key_bindings=kb,
            complete_while_typing=False,
            multiline=True,
            prompt_continuation=lambda *args, **kwargs: "... ",
            history=InMemoryHistory(),
        )

        # Store client and session_id for the key handler
        _client = client
        _session_id = session_id
        _loop = asyncio.get_event_loop()

        # Create a handler for the Enter key so we can deal with multiline input
        @kb.add("enter")
        def _(event):
            buffer = event.app.current_buffer
            text = buffer.document.text

            if is_code_complete(text):
                # Submit to server
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        _client.send_repl_eval(text, _session_id),
                        _loop,
                    )
                    response = future.result(timeout=30)
                except Exception as e:
                    print(f"Error: {e}")
                    buffer.reset()
                    return

                # Save our code to the history
                session.history.append_string(text)

                # Clear buffer
                buffer.reset()

                # Echo input and response manually
                text_display = text.replace("\n", "\n... ")
                print(f">>> {text_display}")

                output = response.get("output", "")
                error = response.get("error")
                if error:
                    print(f"Error: {error}")
                elif output:
                    print(output, end="\n", flush=True)
            else:
                buffer.insert_text("\n")  # Insert a newline instead

        with patch_stdout():
            while True:
                try:
                    session.prompt(">>> ")
                except KeyboardInterrupt:
                    print("\nExiting.")
                    break

        # End the REPL session
        await client.end_repl_session(session_id)


def start_repl(args) -> None:
    if not HAS_PT:
        sys.exit("You need to install prompt_toolkit to use the REPL client.")

    # Start the repl server in qtile
    start_server()

    # Get socket path
    if hasattr(args, "socket") and args.socket:
        socket_path = args.socket
    else:
        socket_path = find_sockfile()

    try:
        asyncio.run(repl_session(socket_path))
    finally:
        stop_server()


def add_subcommand(subparsers, parents):
    parser = subparsers.add_parser("repl", parents=parents, help="Run a qtile REPL session.")
    parser.add_argument(
        "-s",
        "--socket",
        action="store",
        type=str,
        default=None,
        help="Use specified socket for IPC.",
    )
    parser.set_defaults(func=start_repl)
