import asyncio

import pytest

from libqtile import ipc
from libqtile.ipc import MessageType, pack, pack_message, unpack


def test_ipc_json_encoder_supports_sets():
    serialized = pack({"foo": set()})
    assert serialized == b'{"foo": []}'


def test_ipc_json_throws_error_on_unsupported_field():
    class NonSerializableType: ...

    with pytest.raises(
        ValueError,
        match=(
            "Tried to JSON serialize unsupported type <class '"
            "test.test_ipc.test_ipc_json_throws_error_on_unsupported_field.<locals>.NonSerializableType"
            "'>.*"
        ),
    ):
        pack({"foo": NonSerializableType()})


def test_pack_unpack_roundtrip():
    """Test that pack/unpack are inverse operations."""
    test_data = {"command": "test", "args": [1, 2, 3], "kwargs": {"key": "value"}}
    packed = pack(test_data)
    unpacked = unpack(packed)
    assert unpacked == test_data


def test_pack_message_format():
    """Test that pack_message creates correct header format."""
    payload = {"test": "data"}
    message = pack_message(MessageType.COMMAND, payload)

    # Check header: version (1) + type (1) + length (4) = 6 bytes
    assert len(message) >= 6
    assert message[0] == ipc.PROTOCOL_VERSION
    assert message[1] == MessageType.COMMAND

    # Check length field
    import struct

    length = struct.unpack("!L", message[2:6])[0]
    assert length == len(message) - 6


def test_message_types():
    """Test that all message types are defined correctly."""
    assert MessageType.COMMAND == 0x01
    assert MessageType.COMMAND_RESPONSE == 0x02
    assert MessageType.REPL_EVAL == 0x10
    assert MessageType.REPL_EVAL_RESPONSE == 0x11
    assert MessageType.REPL_COMPLETE == 0x12
    assert MessageType.REPL_COMPLETE_RESPONSE == 0x13
    assert MessageType.REPL_SESSION_START == 0x14
    assert MessageType.REPL_SESSION_END == 0x15
    assert MessageType.KEEPALIVE == 0xF0
    assert MessageType.KEEPALIVE_ACK == 0xF1
    assert MessageType.CLOSE == 0xFF


@pytest.mark.asyncio
async def test_read_write_message():
    """Test read_message and write_message functions."""
    # Create a mock reader/writer pair
    reader = asyncio.StreamReader()

    # Create a buffer to capture writes
    written_data = bytearray()

    class MockWriter:
        def write(self, data):
            written_data.extend(data)

        async def drain(self):
            pass

        def close(self):
            pass

        async def wait_closed(self):
            pass

    writer = MockWriter()

    # Test writing a message
    test_payload = {"test": "value", "number": 42}
    await ipc.write_message(writer, MessageType.COMMAND, test_payload)

    # Feed the written data to the reader
    reader.feed_data(bytes(written_data))
    reader.feed_eof()

    # Test reading the message back
    msg_type, payload = await ipc.read_message(reader)
    assert msg_type == MessageType.COMMAND
    assert payload == test_payload


@pytest.mark.asyncio
async def test_read_message_incomplete_header():
    """Test that incomplete header raises appropriate error."""
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x01\x01")  # Only 2 bytes, need 6
    reader.feed_eof()

    with pytest.raises(ipc.IPCError, match="Incomplete message header"):
        await ipc.read_message(reader)


@pytest.mark.asyncio
async def test_read_message_invalid_version():
    """Test that invalid protocol version raises error."""
    reader = asyncio.StreamReader()
    # Version 0x99 (invalid), type 0x01, length 0
    reader.feed_data(b"\x99\x01\x00\x00\x00\x00")
    reader.feed_eof()

    with pytest.raises(ipc.IPCError, match="Unsupported protocol version"):
        await ipc.read_message(reader)


@pytest.mark.asyncio
async def test_read_message_invalid_type():
    """Test that invalid message type raises error."""
    reader = asyncio.StreamReader()
    # Version 0x01, type 0x99 (invalid), length 0
    reader.feed_data(b"\x01\x99\x00\x00\x00\x00")
    reader.feed_eof()

    with pytest.raises(ipc.IPCError, match="Unknown message type"):
        await ipc.read_message(reader)


def test_unpack_invalid_json():
    """Test that invalid JSON raises IPCError."""
    with pytest.raises(ipc.IPCError, match="Unable to decode message payload"):
        unpack(b"not valid json")


def test_unpack_invalid_encoding():
    """Test that invalid UTF-8 raises IPCError."""
    with pytest.raises(ipc.IPCError, match="Unable to decode message payload"):
        unpack(b"\xff\xfe")  # Invalid UTF-8


class TestClient:
    """Tests for the Client class."""

    def test_client_init(self, tmp_path):
        """Test Client initialization."""
        socket_path = str(tmp_path / "test.sock")
        client = ipc.Client(socket_path)
        assert client.socket_path == socket_path


class TestPersistentClient:
    """Tests for the PersistentClient class."""

    def test_persistent_client_init(self, tmp_path):
        """Test PersistentClient initialization."""
        socket_path = str(tmp_path / "test.sock")
        client = ipc.PersistentClient(socket_path)
        assert client.socket_path == socket_path
        assert client.reader is None
        assert client.writer is None


class TestServer:
    """Tests for the Server class."""

    def test_server_creates_socket(self, tmp_path):
        """Test Server creates socket file."""
        socket_path = str(tmp_path / "test.sock")

        def handler(msg):
            return msg

        server = ipc.Server(socket_path, handler)
        assert server.socket_path == socket_path
        assert server.handler == handler
        assert server.repl_handler is None

    def test_server_set_repl_handler(self, tmp_path):
        """Test Server can set REPL handler."""
        socket_path = str(tmp_path / "test.sock")

        def handler(msg):
            return msg

        async def repl_handler(msg_type, payload):
            return {"result": "ok"}

        server = ipc.Server(socket_path, handler)
        assert server.repl_handler is None

        server.set_repl_handler(repl_handler)
        assert server.repl_handler == repl_handler

        server.set_repl_handler(None)
        assert server.repl_handler is None
