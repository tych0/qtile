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

"""
    A simple IPC mechanism for communicating between two local processes. We
    use marshal to serialize data - this means that both client and server must
    run the same Python version, and that clients must be trusted (as
    un-marshalling untrusted data can result in arbitrary code execution).
"""
import marshal
import logging
import os.path
import socket
import struct
import fcntl

from six.moves import asyncio

HDRLEN = 4
BUFSIZE = 1024 * 1024


class IPCError(Exception):
    pass


class _IPC:
    def _unpack(self, data):
        try:
            assert len(data) >= HDRLEN
            size = struct.unpack("!L", data[:HDRLEN])[0]
            assert size >= len(data[HDRLEN:])
            return self._unpack_body(data[HDRLEN:HDRLEN + size])
        except AssertionError:
            raise IPCError(
                "error reading reply!"
                " (probably the socket was disconnected)"
            )

    def _unpack_body(self, body):
        return marshal.loads(body)

    def _pack(self, msg):
        msg = marshal.dumps(msg)
        size = struct.pack("!L", len(msg))
        return size + msg


class _ClientProtocol(asyncio.Protocol, _IPC):
    """IPC Client Protocol

    1. The client is initalized with a Future, which will return the result of
    the query, and a msg, which is sent to the server.

    2. Once the connection is made, the client sends its message to the server,
    then writes an EOF.

    3. The client then recieves data from the server until the server closes
    the connection, signalling that all the data has been sent.

    4. When the connection is closed by the server, the data is unpacked and
    returned.
    """
    def __init__(self, future, msg):
        asyncio.Protocol.__init__(self)
        self.future = future
        self.msg = msg
        self.response = b''

    def connection_made(self, transport):
        transport.write(self._pack(self.msg))
        transport.write_eof()

    def data_received(self, data):
        self.response += data

    def connection_lost(self, exc):
        try:
            data = self._unpack(self.response)
        except IPCError as e:
            self.future.set_exception(e)
        else:
            self.future.set_result(data)


class Client(object):
    def __init__(self, fname):
        self.fname = fname
        self.loop = asyncio.get_event_loop()

    def send(self, msg):
        future = asyncio.Future()
        clientprotocol = _ClientProtocol(future, msg)

        client_coroutine = self.loop.create_unix_connection(lambda: clientprotocol, path=self.fname)

        try:
            self.loop.run_until_complete(client_coroutine)
        except OSError:
            raise IPCError("Could not open %s" % self.fname)

        try:
            self.loop.run_until_complete(asyncio.wait_for(future, timeout=30))
        except asyncio.TimeoutError:
            raise RuntimeError("Server not responding")

        return future.result()

    def call(self, data):
        return self.send(data)


class _ServerProtocol(asyncio.Protocol, _IPC):
    """IPC Server Protocol

    1. The server is initalized with a handler callback function for evaluating
    incoming queries and a log.

    2. Once the connection is made, the server initializes a data store for
    incoming data.

    3. The client sends all its data to the server, which is stored.

    4. The client signals that all data is sent by sending an EOF, at which
    point the server then unpacks the data and runs it through the handler.
    The result is returned to the client and the connection is closed.
    """
    def __init__(self, handler, log):
        asyncio.Protocol.__init__(self)
        self.handler = handler
        self.log = log

    def connection_made(self, transport):
        self.transport = transport
        self.log.info('Connection made to server')
        self.data = b''

    def data_received(self, recv):
        self.log.info('Data recieved by server')
        self.data += recv

    def eof_received(self):
        self.log.info('EOF recieved by server')
        try:
            req = self._unpack(self.data)
        except IPCError:
            self.log.info('Invalid data received, closing connection')
            self.transport.close()
            return
        rep = self.handler(req)
        result = self._pack(rep)
        self.log.info('Sending result on receive EOF')
        self.transport.write(result)
        self.log.info('Closing connection on receive EOF')
        self.transport.close()
        self.data = None


class Server(object):
    def __init__(self, fname, handler):
        self.log = logging.getLogger('qtile')
        self.fname = fname
        self.handler = handler
        self.loop = asyncio.get_event_loop()

        if os.path.exists(fname):
            os.unlink(fname)

        self.sock = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
            0
        )
        flags = fcntl.fcntl(self.sock, fcntl.F_GETFD)
        fcntl.fcntl(self.sock, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
        self.sock.bind(self.fname)

    def close(self):
        self.log.info('Stopping server on server close')
        self.server.close()
        self.sock.close()

    def start(self):
        serverprotocol = _ServerProtocol(self.handler, self.log)
        server_coroutine = self.loop.create_unix_server(lambda: serverprotocol, sock=self.sock, backlog=5)

        self.log.info('Starting server')
        self.server = self.loop.run_until_complete(server_coroutine)
