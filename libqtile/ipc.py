# Copyright (c) 2008, Aldo Cortesi. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from __future__ import annotations

import asyncio
import fcntl
import json
import os.path
import socket
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from libqtile.log_utils import logger
from libqtile.utils import create_task, get_cache_dir

SOCKBASE = "qtilesocket.%s"
MESSAGE_TYPE = "message_type"
CONTENT = "content"


class IPCError(Exception):
    pass


class MessageType(StrEnum):
    Command = "command"


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


class Client:
    def __init__(self, socket_path: str, message_type: MessageType) -> None:
        """Create a new IPC client

        Parameters
        ----------
        socket_path: str
            The file path to the file that is used to open the connection to
            the running IPC server.
        message_type: MessageType
            The type of messages this client will send.
        """
        self.message_type = message_type
        self.socket_path = socket_path

    def __enter__(self):
        try:
            self.reader, self.writer = asyncio.run(
                asyncio.wait_for(asyncio.open_unix_connection(path=self.socket_path), timeout=3)
            )
        except (ConnectionRefusedError, FileNotFoundError) as e:
            raise IPCError(f"Could not open {self.socket_path}: {str(e)}")

    def __exit__(self):
        self.writer.close()
        await self.writer.wait_closed()

    def send(self, msg: Any) -> Any:
        """Send the message and return the response from the server

        If any exception is raised by the server, that will propogate out of
        this call.
        """
        return asyncio.run(self.async_send(msg))

    async def async_send(self, msg: Any) -> Any:
        """Send the message to the server, and wait for a response. Does not
        disconnect from the server.
        """

        try:
            encoded = json.dumps({MESSAGE_TYPE: self.message_type, CONTENT: msg}).encode()
            self.writer.write(encoded)
            self.writer.write("\n")

            raw = await asyncio.wait_for(self.reader.readline(), timeout=10)
            decoded = json.loads(raw)
            if decoded[MESSAGE_TYPE] != self.message_type:
                raise IPCError(f"unexpected response type {decoded[MESSAGE_TYPE]}")

            return decoded[CONTENT]
        except asyncio.TimeoutError:
            raise IPCError("Server not responding")


class Server:
    def __init__(self, socket_path: str, handler: Callable[[MessageType, Any], Any]) -> None:
        self.socket_path = socket_path
        self.handler = handler
        self.server = None  # type: asyncio.AbstractServer | None

        if os.path.exists(socket_path):
            os.unlink(socket_path)

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        flags = fcntl.fcntl(self.sock.fileno(), fcntl.F_GETFD)
        fcntl.fcntl(self.sock.fileno(), fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
        self.sock.bind(self.socket_path)

    async def server_main(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                raw = await reader.readline()
                decoded = json.loads(raw)
                response = self.handler(decoded[MESSAGE_TYPE], decoded[CONTENT])
                encoded = json.dumps(
                    {MESSAGE_TYPE: decoded[MESSAGE_TYPE], CONTENT: response}
                ).encode()
                writer.write(encoded)
                writer.write(b"\n")
        except asyncio.IncompleteReadError:
            pass

    async def _server_callback(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Callback when a connection is made to the server

        Read the data sent from the client, execute the requested command, and
        send the reply back to the client.
        """
        logger.debug("Connection made to server")
        create_task(self.server_main(reader, writer))

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
