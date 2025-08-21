import asyncio
import ctypes
import ctypes.util
import os
import struct

from libqtile import bar
from libqtile.log_utils import logger
from libqtile.widget import base

# inotify constants
IN_ACCESS = 0x00000001
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_CLOSE_NOWRITE = 0x00000010
IN_OPEN = 0x00000020
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800

# Combined flags
IN_CLOSE = IN_CLOSE_WRITE | IN_CLOSE_NOWRITE
IN_MOVE = IN_MOVED_FROM | IN_MOVED_TO
IN_ALL_EVENTS = (
    IN_ACCESS
    | IN_MODIFY
    | IN_ATTRIB
    | IN_CLOSE_WRITE
    | IN_CLOSE_NOWRITE
    | IN_OPEN
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
)

# Event structure: struct inotify_event { int wd; uint32_t mask; uint32_t cookie; uint32_t len; char name[]; }
INOTIFY_EVENT_SIZE = struct.calcsize("iIII")

# Load libc
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

# Define function signatures
inotify_init = libc.inotify_init
inotify_init.argtypes = []
inotify_init.restype = ctypes.c_int

inotify_add_watch = libc.inotify_add_watch
inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
inotify_add_watch.restype = ctypes.c_int

inotify_rm_watch = libc.inotify_rm_watch
inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
inotify_rm_watch.restype = ctypes.c_int


class InotifyEvent:
    """Represents an inotify event"""

    def __init__(self, wd: int, mask: int, cookie: int, name: str):
        self.wd = wd
        self.mask = mask
        self.cookie = cookie
        self.name = name

    def __repr__(self):
        return f"InotifyEvent(wd={self.wd}, mask={self.mask:x}, cookie={self.cookie}, name='{self.name}')"


class InotifyWidget(base._Widget):
    """A widget that watches files using inotify and calls process_event() when changes occur"""

    defaults = [
        ("files", None, "List of files to watch"),
        ("mask", IN_ALL_EVENTS, "inotify mask for events to watch"),
    ]

    def __init__(self, length=bar.CALCULATED, **config):
        base._Widget.__init__(self, length, **config)
        self.add_defaults(InotifyWidget.defaults)
        self.inotify_fd: int | None = None
        self.watches: dict[str, int] = {}  # filename -> watch descriptor
        self.wd_to_file: dict[int, str] = {}  # watch descriptor -> filename

    def _configure(self, qtile, bar):
        base._Widget._configure(self, qtile, bar)

        if self.files:
            self._setup_inotify()

    def _setup_inotify(self):
        """Initialize inotify and add file watches"""
        try:
            # Initialize inotify
            self.inotify_fd = inotify_init()
            if self.inotify_fd == -1:
                errno = ctypes.get_errno()
                raise OSError(errno, f"inotify_init failed: {os.strerror(errno)}")

            # Add watches for each file
            for filepath in self.files:
                self._add_watch(filepath)

            # Add the inotify fd to the asyncio event loop
            try:
                loop = asyncio.get_event_loop()
                loop.add_reader(self.inotify_fd, self._handle_inotify_events)
            except RuntimeError as e:
                if (
                    "no running event loop" in str(e).lower()
                    or "event loop is closed" in str(e).lower()
                ):
                    logger.warning("No running event loop, inotify events will not be processed")
                else:
                    raise

            logger.info(f"InotifyWidget: watching {len(self.watches)} files")

        except Exception as e:
            logger.exception(f"Failed to setup inotify: {e}")
            if self.inotify_fd is not None:
                os.close(self.inotify_fd)
                self.inotify_fd = None

    def _add_watch(self, filepath: str):
        """Add a watch for a specific file"""
        try:
            wd = inotify_add_watch(self.inotify_fd, filepath.encode("utf-8"), self.mask)
            if wd == -1:
                errno = ctypes.get_errno()
                logger.warning(f"Failed to watch {filepath}: {os.strerror(errno)}")
                return

            self.watches[filepath] = wd
            self.wd_to_file[wd] = filepath
            logger.debug(f"Added watch for {filepath} (wd={wd})")

        except Exception as e:
            logger.exception(f"Failed to add watch for {filepath}: {e}")

    def _handle_inotify_events(self):
        """Handle inotify events from the file descriptor"""
        try:
            # Read events from inotify fd
            data = os.read(self.inotify_fd, 4096)
            offset = 0

            while offset < len(data):
                # Parse inotify_event structure
                wd, mask, cookie, name_len = struct.unpack_from("iIII", data, offset)
                offset += INOTIFY_EVENT_SIZE

                # Read the name if present
                name = ""
                if name_len > 0:
                    name = (
                        data[offset : offset + name_len]
                        .rstrip(b"\x00")
                        .decode("utf-8", errors="replace")
                    )
                    offset += name_len

                # Get the filename from watch descriptor
                filepath = self.wd_to_file.get(wd, "")

                # Create event object
                event = InotifyEvent(wd, mask, cookie, name)

                # Call the process_event method
                self.process_event(filepath, event)

        except Exception as e:
            logger.exception(f"Error handling inotify events: {e}")

    def process_event(self, filepath: str, event: InotifyEvent):
        """Override this method to handle inotify events

        Args:
            filepath: The file path that was watched
            event: The InotifyEvent object containing event details
        """
        logger.debug(f"File event: {filepath} - {event}")

    def finalize(self):
        """Clean up inotify resources"""
        if self.inotify_fd is not None:
            try:
                # Remove from event loop
                try:
                    loop = asyncio.get_event_loop()
                    loop.remove_reader(self.inotify_fd)
                except RuntimeError:
                    # Event loop may be closed during testing
                    pass

                # Remove all watches
                for wd in self.watches.values():
                    inotify_rm_watch(self.inotify_fd, wd)

                # Close inotify fd
                os.close(self.inotify_fd)

            except Exception as e:
                logger.exception(f"Error during inotify cleanup: {e}")
            finally:
                self.inotify_fd = None
                self.watches.clear()
                self.wd_to_file.clear()

        try:
            base._Widget.finalize(self)
        except AttributeError:
            # Handle case where _futures contains None during testing
            pass


class SimpleFileWatcher(InotifyWidget):
    """Example implementation that shows file change notifications"""

    defaults = [
        ("format", "File changed: {filepath}", "Format string for display"),
    ]

    def __init__(self, length=bar.CALCULATED, **config):
        InotifyWidget.__init__(self, length, **config)
        self.add_defaults(SimpleFileWatcher.defaults)

    def process_event(self, filepath: str, event: InotifyEvent):
        """Update widget text when files change"""
        # Update the widget text
        self.text = self.format.format(filepath=filepath, event=event)
        self.bar.draw()

        # Log the event
        logger.info(f"File watcher: {filepath} changed (mask={event.mask:x})")
