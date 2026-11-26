import pytest

pytestmark = pytest.mark.parametrize("test_client", ["cursor-shape"], indirect=True)


@pytest.mark.parametrize("shape", ["crosshair", "text", "wait", "help", "grab"])
def test_cursor_shape_protocol(test_client, wmanager, shape):
    """Test that the C client can successfully request shapes via the protocol."""

    def cursor_name():
        return wmanager.c.core.get_cursor_shape_v1()

    # assert_ok() already round-trips with the compositor, so the window is
    # fully mapped by the time it returns.
    test_client.assert_ok(shape)
    assert len(wmanager.c.windows()) > 0
    wmanager.c.window.set_position_floating(150, 150)

    # Cursor is outside window so should be default
    wmanager.c.core.eval("self.warp_pointer(0, 0, motion=True)")
    assert cursor_name() == "default"

    # Move cursor inside test client window
    wmanager.c.core.eval("self.warp_pointer(200, 200, motion=True)")
    wmanager.c.sync()
    assert cursor_name() != "default"
    cursor = cursor_name()

    if shape == "wait":
        assert cursor in ["wait", "watch"]
    elif shape == "help":
        assert cursor in ["help", "whats_this", "question_arrow"]
    else:
        assert cursor == shape
