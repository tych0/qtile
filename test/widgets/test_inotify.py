#!/usr/bin/env python3
"""Test cases for the inotify widget"""

import tempfile
from pathlib import Path

from libqtile.widget.inotify import InotifyWidget, SimpleFileWatcher
from test.widgets.conftest import FakeBar


class FileWatcherForTesting(InotifyWidget):
    """Test implementation that tracks events"""

    def __init__(self, **config):
        super().__init__(**config)
        self.events = []

    def process_event(self, filepath: str, event):
        """Track events for testing"""
        self.events.append((filepath, event.mask, event.name))


def test_inotify_widget_basic(fake_qtile, fake_window):
    """Test basic inotify widget functionality"""

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
        test_file = tf.name
        tf.write("initial content\n")

    try:
        # Create widget with the test file
        widget = FileWatcherForTesting(files=[test_file])

        # Use the provided fixtures
        fake_bar = FakeBar([], window=fake_window)

        # Configure the widget
        widget._configure(fake_qtile, fake_bar)

        # Verify inotify was set up (even without event loop)
        assert widget.inotify_fd is not None, "inotify should be initialized"
        assert len(widget.watches) == 1, "Should have one watch"
        assert test_file in widget.watches, "Should watch the test file"

        # Test the process_event method directly since we can't rely on asyncio in tests
        from libqtile.widget.inotify import InotifyEvent

        event = InotifyEvent(1, 0x2, 0, "test")
        widget.process_event(test_file, event)

        # Check if the event was recorded
        assert len(widget.events) == 1, "Should have recorded one event"
        assert widget.events[0][0] == test_file, "Event should reference the correct file"

        # Clean up
        widget.finalize()

    finally:
        # Clean up test file
        Path(test_file).unlink(missing_ok=True)


def test_inotify_widget_no_files(fake_qtile, fake_window):
    """Test widget with no files configured"""
    widget = InotifyWidget(files=None)

    fake_bar = FakeBar([], window=fake_window)

    # Should not raise an exception
    widget._configure(fake_qtile, fake_bar)
    assert widget.inotify_fd is None

    # Clean up
    widget.finalize()


def test_simple_file_watcher(fake_qtile, fake_window):
    """Test the SimpleFileWatcher implementation"""
    widget = SimpleFileWatcher(files=["/nonexistent"], format="Changed: {filepath}")

    fake_bar = FakeBar([], window=fake_window)

    # Configure widget (should handle nonexistent file gracefully)
    widget._configure(fake_qtile, fake_bar)

    # Test process_event
    from libqtile.widget.inotify import InotifyEvent

    event = InotifyEvent(1, 0x2, 0, "test")
    widget.process_event("/test/file", event)

    assert "Changed: /test/file" in widget.text

    # Clean up
    widget.finalize()
