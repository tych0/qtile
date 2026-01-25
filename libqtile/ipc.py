"""
A simple IPC mechanism for communicating between two local processes.

Uses a framed protocol with JSON serialization:
- 1 byte protocol version
- 1 byte message type
- 4 bytes big-endian payload length
- Variable length JSON payload

Supports stateful connections with multiple messages per connection.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os.path
import socket
import struct
from enum import IntEnum
from typing import Any

from libqtile import hook
from libqtile.log_utils import logger
from libqtile.utils import get_cache_dir

# Protocol constants
PROTOCOL_VERSION = 0x01
HEADER_FORMAT = "!BBL"  # version (1 byte), type (1 byte), length (4 bytes big-endian)
HEADER_LENGTH = struct.calcsize(HEADER_FORMAT)

SOCKBASE = "qtilesocket.%s"


class MessageType(IntEnum):
    """Message types for the IPC protocol."""

    # Command messages (existing functionality)
    COMMAND = 0x01
    COMMAND_RESPONSE = 0x02

    # REPL messages
    REPL_EVAL = 0x10
    REPL_EVAL_RESPONSE = 0x11
    REPL_COMPLETE = 0x12
    REPL_COMPLETE_RESPONSE = 0x13
    REPL_SESSION_START = 0x14
    REPL_SESSION_END = 0x15

    # Connection control
    KEEPALIVE = 0xF0
    KEEPALIVE_ACK = 0xF1
    CLOSE = 0xFF


class IPCError(Exception):
    pass


def find_sockfile(display: str | None = None):
    """
    Finds the appropriate socket file for the given display.

    If unspecified, the socket file is determined as follows:

        - If WAYLAND_DISPLAY is set, use it.
        - else if DISPLAY is set, use that.
        - else check for the existence of a socket file for WAYLAND_DISPLAY=wayland-0
          and if it exists, use it.
        - else check for the existence of a socket file for DISPLAY=:0
          and if it exists, use it.
        - else raise an IPCError.

    """
    cache_directory = get_cache_dir()

    if display:
        return os.path.join(cache_directory, SOCKBASE % display)

    display = os.environ.get("WAYLAND_DISPLAY")
    if display:
        return os.path.join(cache_directory, SOCKBASE % display)

    display = os.environ.get("DISPLAY")
    if display:
        return os.path.join(cache_directory, SOCKBASE % display)

    sockfile = os.path.join(cache_directory, SOCKBASE % "wayland-0")
    if os.path.exists(sockfile):
        return sockfile

    sockfile = os.path.join(cache_directory, SOCKBASE % ":0")
    if os.path.exists(sockfile):
        return sockfile

    raise IPCError("Could not find socket file.")


def _json_encoder(field: Any) -> Any:
    """Convert non-serializable types to ones understood by stdlib json module"""
    if isinstance(field, set):
        return list(field)
    raise ValueError(f"Tried to JSON serialize unsupported type {type(field)}: {field}")


def pack(msg: Any) -> bytes:
    """Pack the object into a JSON message payload"""
    json_obj = json.dumps(msg, default=_json_encoder)
    return json_obj.encode()


def unpack(data: bytes) -> Any:
    """Unpack a JSON message payload"""
    try:
        return json.loads(data.decode())
    except (ValueError, UnicodeDecodeError) as e:
        raise IPCError("Unable to decode message payload") from e


def pack_message(msg_type: MessageType, payload: Any) -> bytes:
    """Pack a complete message with header and JSON payload."""
    payload_bytes = pack(payload)
    header = struct.pack(HEADER_FORMAT, PROTOCOL_VERSION, msg_type, len(payload_bytes))
    return header + payload_bytes


async def read_message(reader: asyncio.StreamReader) -> tuple[MessageType, Any]:
    """Read a framed message from the stream.

    Returns:
        tuple of (message_type, payload)

    Raises:
        IPCError: If the message cannot be read or decoded
        asyncio.IncompleteReadError: If the connection is closed
    """
    try:
        header = await reader.readexactly(HEADER_LENGTH)
    except asyncio.IncompleteReadError as e:
        if len(e.partial) == 0:
            raise  # Connection closed cleanly
        raise IPCError("Incomplete message header") from e

    version, msg_type, length = struct.unpack(HEADER_FORMAT, header)

    if version != PROTOCOL_VERSION:
        raise IPCError(f"Unsupported protocol version: {version}")

    try:
        msg_type = MessageType(msg_type)
    except ValueError as e:
        raise IPCError(f"Unknown message type: {msg_type}") from e

    if length > 0:
        try:
            payload_bytes = await reader.readexactly(length)
        except asyncio.IncompleteReadError as e:
            raise IPCError("Incomplete message payload") from e
        payload = unpack(payload_bytes)
    else:
        payload = None

    return msg_type, payload


async def write_message(
    writer: asyncio.StreamWriter, msg_type: MessageType, payload: Any
) -> None:
    """Write a framed message to the stream."""
    message = pack_message(msg_type, payload)
    writer.write(message)
    await writer.drain()


class Client:
    """Synchronous IPC client for single request/response exchanges."""

    def __init__(self, socket_path: str) -> None:
        """Create a new IPC client

        Parameters
        ----------
        socket_path: str
            The file path to the file that is used to open the connection to
            the running IPC server.
        """
        self.socket_path = socket_path

    def call(self, data: Any) -> Any:
        return self.send(data)

    def send(self, msg: Any) -> Any:
        """Send the message and return the response from the server

        If any exception is raised by the server, that will propogate out of
        this call.
        """
        return asyncio.run(self.async_send(msg))

    async def async_send(self, msg: Any) -> Any:
        """Send a command message to the server and return the response."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(path=self.socket_path), timeout=3
            )
        except (ConnectionRefusedError, FileNotFoundError):
            raise IPCError(f"Could not open {self.socket_path}")

        try:
            await write_message(writer, MessageType.COMMAND, msg)

            msg_type, response = await asyncio.wait_for(read_message(reader), timeout=10)

            if msg_type != MessageType.COMMAND_RESPONSE:
                raise IPCError(f"Unexpected response type: {msg_type}")

            return response
        except asyncio.TimeoutError:
            raise IPCError("Server not responding")
        finally:
            writer.close()
            await writer.wait_closed()


class PersistentClient:
    """Async IPC client for stateful connections with multiple message exchanges."""

    def __init__(self, socket_path: str) -> None:
        """Create a new persistent IPC client.

        Parameters
        ----------
        socket_path: str
            The file path to the unix socket.
        """
        self.socket_path = socket_path
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        """Establish a connection to the server."""
        if self.writer is not None:
            return  # Already connected

        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_unix_connection(path=self.socket_path), timeout=3
            )
        except (ConnectionRefusedError, FileNotFoundError):
            raise IPCError(f"Could not open {self.socket_path}")

    async def close(self) -> None:
        """Close the connection gracefully."""
        if self.writer is None:
            return

        try:
            await write_message(self.writer, MessageType.CLOSE, None)
        except Exception:
            pass  # Best effort

        self.writer.close()
        await self.writer.wait_closed()
        self.reader = None
        self.writer = None

    async def send_command(self, msg: Any) -> Any:
        """Send a command and receive the response."""
        if self.writer is None or self.reader is None:
            raise IPCError("Not connected")

        await write_message(self.writer, MessageType.COMMAND, msg)

        msg_type, response = await asyncio.wait_for(read_message(self.reader), timeout=10)

        if msg_type != MessageType.COMMAND_RESPONSE:
            raise IPCError(f"Unexpected response type: {msg_type}")

        return response

    async def send_repl_eval(self, code: str, session_id: str | None = None) -> Any:
        """Send REPL code for evaluation."""
        if self.writer is None or self.reader is None:
            raise IPCError("Not connected")

        payload = {"code": code}
        if session_id:
            payload["session_id"] = session_id

        await write_message(self.writer, MessageType.REPL_EVAL, payload)

        msg_type, response = await asyncio.wait_for(read_message(self.reader), timeout=30)

        if msg_type != MessageType.REPL_EVAL_RESPONSE:
            raise IPCError(f"Unexpected response type: {msg_type}")

        return response

    async def send_repl_complete(self, text: str, session_id: str | None = None) -> list[str]:
        """Send REPL completion request."""
        if self.writer is None or self.reader is None:
            raise IPCError("Not connected")

        payload = {"text": text}
        if session_id:
            payload["session_id"] = session_id

        await write_message(self.writer, MessageType.REPL_COMPLETE, payload)

        msg_type, response = await asyncio.wait_for(read_message(self.reader), timeout=10)

        if msg_type != MessageType.REPL_COMPLETE_RESPONSE:
            raise IPCError(f"Unexpected response type: {msg_type}")

        return response.get("completions", [])

    async def start_repl_session(self) -> str:
        """Start a new REPL session and return the session ID."""
        if self.writer is None or self.reader is None:
            raise IPCError("Not connected")

        await write_message(self.writer, MessageType.REPL_SESSION_START, {})

        msg_type, response = await asyncio.wait_for(read_message(self.reader), timeout=10)

        if msg_type != MessageType.REPL_EVAL_RESPONSE:
            raise IPCError(f"Unexpected response type: {msg_type}")

        return response.get("session_id", "")

    async def end_repl_session(self, session_id: str) -> None:
        """End a REPL session."""
        if self.writer is None or self.reader is None:
            raise IPCError("Not connected")

        await write_message(self.writer, MessageType.REPL_SESSION_END, {"session_id": session_id})

    async def __aenter__(self) -> PersistentClient:
        await self.connect()
        return self

    async def __aexit__(self, _exc_type, _exc_value, _tb) -> None:
        await self.close()


class Server:
    def __init__(self, socket_path: str, handler, repl_handler=None) -> None:
        """Create a new IPC server.

        Parameters
        ----------
        socket_path: str
            The file path for the unix socket.
        handler: callable
            The handler for COMMAND messages. Takes the command payload and
            returns a response.
        repl_handler: callable, optional
            The handler for REPL messages. If None, REPL functionality is disabled.
        """
        self.socket_path = socket_path
        self.handler = handler
        self.repl_handler = repl_handler
        self.server: asyncio.AbstractServer | None = None

        # Use a flag to indicate if session is locked
        self.locked = asyncio.Event()
        hook.subscribe.locked(self.lock)
        hook.subscribe.unlocked(self.unlock)

        if os.path.exists(socket_path):
            os.unlink(socket_path)

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        flags = fcntl.fcntl(self.sock.fileno(), fcntl.F_GETFD)
        fcntl.fcntl(self.sock.fileno(), fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
        self.sock.bind(self.socket_path)

    def lock(self):
        self.locked.set()

    def unlock(self):
        self.locked.clear()

    def set_repl_handler(self, handler) -> None:
        """Set or update the REPL handler."""
        self.repl_handler = handler

    async def _server_callback(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Callback when a connection is made to the server.

        Handles a stateful connection that can process multiple messages.
        """
        logger.debug("Connection made to server")

        try:
            while True:
                try:
                    msg_type, payload = await read_message(reader)
                except asyncio.IncompleteReadError:
                    # Connection closed
                    logger.debug("Client disconnected")
                    break
                except IPCError as e:
                    logger.warning("Invalid message received: %s", e)
                    break

                logger.debug("Received message type: %s", msg_type.name)

                if msg_type == MessageType.CLOSE:
                    logger.debug("Received close request")
                    break

                if msg_type == MessageType.KEEPALIVE:
                    await write_message(writer, MessageType.KEEPALIVE_ACK, None)
                    continue

                if msg_type == MessageType.COMMAND:
                    # Don't handle requests when session is locked
                    if self.locked.is_set():
                        response = (1, {"error": "Session locked."})
                    else:
                        response = self.handler(payload)
                    await write_message(writer, MessageType.COMMAND_RESPONSE, response)
                    continue

                # REPL messages
                if msg_type in (
                    MessageType.REPL_EVAL,
                    MessageType.REPL_COMPLETE,
                    MessageType.REPL_SESSION_START,
                    MessageType.REPL_SESSION_END,
                ):
                    if self.repl_handler is None:
                        repl_response: dict[str, Any] = {
                            "error": "REPL not enabled. Run start_repl_server first."
                        }
                        if msg_type == MessageType.REPL_EVAL:
                            await write_message(
                                writer, MessageType.REPL_EVAL_RESPONSE, repl_response
                            )
                        elif msg_type == MessageType.REPL_COMPLETE:
                            await write_message(
                                writer, MessageType.REPL_COMPLETE_RESPONSE, repl_response
                            )
                        else:
                            await write_message(
                                writer, MessageType.REPL_EVAL_RESPONSE, repl_response
                            )
                    else:
                        repl_response = await self.repl_handler(msg_type, payload)
                        if msg_type == MessageType.REPL_EVAL:
                            await write_message(
                                writer, MessageType.REPL_EVAL_RESPONSE, repl_response
                            )
                        elif msg_type == MessageType.REPL_COMPLETE:
                            await write_message(
                                writer, MessageType.REPL_COMPLETE_RESPONSE, repl_response
                            )
                        elif msg_type == MessageType.REPL_SESSION_START:
                            await write_message(
                                writer, MessageType.REPL_EVAL_RESPONSE, repl_response
                            )
                        # REPL_SESSION_END doesn't need a response
                    continue

                logger.warning("Unhandled message type: %s", msg_type)

        except Exception as e:
            logger.error("Error in server callback: %s", e)
        finally:
            writer.close()
            await writer.wait_closed()
            logger.debug("Connection closed")

    async def __aenter__(self) -> Server:
        """Start and return the server"""
        await self.start()
        return self

    async def __aexit__(self, _exc_type, _exc_value, _tb) -> None:
        """Close and shutdown the server"""
        await self.close()

    async def start(self) -> None:
        """Start the server"""
        assert self.server is None

        logger.debug("Starting server")
        server_coroutine = asyncio.start_unix_server(self._server_callback, sock=self.sock)
        self.server = await server_coroutine

    async def close(self) -> None:
        """Close and shutdown the server"""
        assert self.server is not None

        logger.debug("Stopping server on close")
        self.server.close()
        await self.server.wait_closed()

        self.server = None
