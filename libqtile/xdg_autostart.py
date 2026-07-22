"""
An implementation of the freedesktop.org Desktop Application Autostart
Specification:

    https://specifications.freedesktop.org/autostart-spec/autostart-spec-latest.html

Desktop entry (.desktop) files found in the autostart directories are
launched when qtile first starts (i.e. once per session, not on restarts
or config reloads). The autostart directories are, in order of decreasing
precedence, $XDG_CONFIG_HOME/autostart followed by each directory in
$XDG_CONFIG_DIRS/autostart. Entries are parsed and filtered according to
the Desktop Entry Specification:

    https://specifications.freedesktop.org/desktop-entry-spec/latest/
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from libqtile.log_utils import logger
from libqtile.utils import guess_terminal

DESKTOP_ENTRY_GROUP = "Desktop Entry"

# The desktop name used to match OnlyShowIn/NotShowIn when
# $XDG_CURRENT_DESKTOP is not set.
DEFAULT_DESKTOP_NAME = "qtile"


class DesktopEntryError(Exception):
    """Raised when a .desktop file cannot be parsed."""


def _unescape_string(value: str) -> str:
    r"""
    Unescape a string value from a desktop entry file.

    The escape sequences \s, \n, \t, \r, and \\ are supported for values
    of type string and localestring, meaning ASCII space, newline, tab,
    carriage return, and backslash, respectively.
    """
    result = []
    i = 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value):
            n = value[i + 1]
            if n == "s":
                result.append(" ")
            elif n == "n":
                result.append("\n")
            elif n == "t":
                result.append("\t")
            elif n == "r":
                result.append("\r")
            elif n == "\\":
                result.append("\\")
            else:
                # Not a recognized escape; keep it as-is.
                result.append(c)
                result.append(n)
            i += 2
        else:
            result.append(c)
            i += 1
    return "".join(result)


def _parse_string_list(value: str) -> list[str]:
    r"""
    Parse a semicolon-separated list of strings, where a literal semicolon
    within a value is escaped as \;. A trailing (unescaped) semicolon
    terminates the last entry rather than introducing an empty one.
    """
    entries = []
    current = []
    i = 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value) and value[i + 1] == ";":
            current.append(";")
            i += 2
        elif c == ";":
            entries.append("".join(current))
            current = []
            i += 1
        else:
            current.append(c)
            i += 1
    if current:
        entries.append("".join(current))
    return [_unescape_string(e) for e in entries]


def _parse_boolean(value: str) -> bool:
    return value == "true"


def parse_desktop_file(path: Path) -> dict[str, str]:
    """
    Parse a desktop entry file, returning the keys of its "Desktop Entry"
    group as a dict. Values are returned raw, i.e. without any unescaping,
    since the escaping rules depend on the type of each key.
    """
    keys: dict[str, str] = {}
    in_entry_group = False
    seen_entry_group = False

    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.startswith("["):
                header = line.strip()
                if not header.endswith("]"):
                    raise DesktopEntryError(f"{path}:{lineno}: malformed group header")
                group = header[1:-1]
                in_entry_group = group == DESKTOP_ENTRY_GROUP
                if in_entry_group:
                    if seen_entry_group:
                        raise DesktopEntryError(f"{path}:{lineno}: duplicate group '{group}'")
                    seen_entry_group = True
                continue
            if not in_entry_group:
                continue
            if "=" not in line:
                raise DesktopEntryError(f"{path}:{lineno}: expected key=value")
            key, _, value = line.partition("=")
            keys[key.strip()] = value.strip()

    if not seen_entry_group:
        raise DesktopEntryError(f"{path}: no [Desktop Entry] group")
    return keys


def parse_exec(exec_string: str) -> list[str]:
    """
    Split an (already string-unescaped) Exec value into arguments,
    following the quoting rules of the Desktop Entry Specification:
    arguments are separated by spaces and may be quoted with double
    quotes; within a quoted argument, a backslash escapes the next
    character.
    """
    args: list[str] = []
    current: list[str] = []
    have_arg = False
    in_quote = False
    i = 0
    while i < len(exec_string):
        c = exec_string[i]
        if in_quote:
            if c == "\\":
                if i + 1 >= len(exec_string):
                    raise DesktopEntryError("trailing backslash in Exec")
                current.append(exec_string[i + 1])
                i += 2
                continue
            elif c == '"':
                in_quote = False
            else:
                current.append(c)
        elif c == '"':
            in_quote = True
            have_arg = True
        elif c == " ":
            if have_arg or current:
                args.append("".join(current))
                current = []
                have_arg = False
        else:
            current.append(c)
        i += 1
    if in_quote:
        raise DesktopEntryError("unterminated quote in Exec")
    if have_arg or current:
        args.append("".join(current))
    return args


def _expand_field_codes(args: list[str], entry: AutostartEntry) -> list[str]:
    """
    Expand (or drop) the %-style field codes of the Desktop Entry
    Specification. Autostarted applications are launched without any file
    or URL arguments, so the file-list field codes expand to nothing.
    """
    expanded: list[str] = []
    for arg in args:
        if arg in ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m"):
            # An argument that is a lone file-list (or deprecated) field
            # code is dropped entirely.
            continue
        if arg == "%i":
            icon = entry.keys.get("Icon")
            if icon:
                expanded.extend(["--icon", _unescape_string(icon)])
            continue
        result = []
        i = 0
        while i < len(arg):
            c = arg[i]
            if c == "%" and i + 1 < len(arg):
                code = arg[i + 1]
                if code == "%":
                    result.append("%")
                elif code == "c":
                    result.append(_unescape_string(entry.keys.get("Name", "")))
                elif code == "k":
                    result.append(str(entry.path))
                # Any other field code embedded in an argument expands to
                # nothing.
                i += 2
                continue
            result.append(c)
            i += 1
        expanded.append("".join(result))
    return expanded


@dataclass
class AutostartEntry:
    """A parsed desktop entry from an autostart directory."""

    path: Path
    keys: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> AutostartEntry:
        return cls(path=path, keys=parse_desktop_file(path))

    @property
    def name(self) -> str:
        return _unescape_string(self.keys.get("Name", self.path.stem))

    def command(self) -> list[str]:
        """The argument vector to execute for this entry."""
        exec_value = self.keys.get("Exec", "")
        if not exec_value:
            raise DesktopEntryError(f"{self.path}: no Exec key")
        args = parse_exec(_unescape_string(exec_value))
        args = _expand_field_codes(args, self)
        if not args:
            raise DesktopEntryError(f"{self.path}: empty Exec key")
        return args

    def should_autostart(self, desktops: list[str]) -> bool:
        """
        Whether this entry should be started in the desktop environment
        named by ``desktops`` (the entries of $XDG_CURRENT_DESKTOP).
        """
        if self.keys.get("Type", "Application") != "Application":
            return False

        # Hidden means the user has "deleted" the entry.
        if _parse_boolean(self.keys.get("Hidden", "false")):
            return False

        if "OnlyShowIn" in self.keys:
            only_show_in = _parse_string_list(self.keys["OnlyShowIn"])
            if not any(d in only_show_in for d in desktops):
                return False
        if "NotShowIn" in self.keys:
            not_show_in = _parse_string_list(self.keys["NotShowIn"])
            if any(d in not_show_in for d in desktops):
                return False

        # TryExec: the entry is only valid if the given executable exists.
        try_exec = self.keys.get("TryExec")
        if try_exec:
            try_exec = _unescape_string(try_exec)
            if os.path.isabs(try_exec):
                if not os.access(try_exec, os.X_OK):
                    return False
            elif shutil.which(try_exec) is None:
                return False

        return True


def autostart_directories(env: Mapping[str, str] | None = None) -> list[Path]:
    """
    The autostart directories, in order of decreasing precedence, per the
    XDG Base Directory Specification.
    """
    if env is None:
        env = os.environ
    config_home = Path(env.get("XDG_CONFIG_HOME") or "~/.config").expanduser()
    dirs = [config_home / "autostart"]
    config_dirs = env.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    for config_dir in config_dirs.split(":"):
        if config_dir:
            dirs.append(Path(config_dir).expanduser() / "autostart")
    return dirs


def scan_autostart_entries(
    directories: list[Path] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[AutostartEntry]:
    """
    Collect the desktop entries that should be autostarted.

    Entries are deduplicated by desktop file ID (their filename): when the
    same ID exists in several autostart directories, only the one from the
    highest-precedence directory is considered. Entries excluded by
    Hidden, OnlyShowIn/NotShowIn (matched against $XDG_CURRENT_DESKTOP),
    or TryExec are filtered out.
    """
    if env is None:
        env = os.environ
    if directories is None:
        directories = autostart_directories(env)

    desktops = [d for d in env.get("XDG_CURRENT_DESKTOP", "").split(":") if d]
    if not desktops:
        desktops = [DEFAULT_DESKTOP_NAME]

    files: dict[str, Path] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix != ".desktop" or not path.is_file():
                continue
            # First (highest-precedence) directory wins.
            files.setdefault(path.name, path)

    entries = []
    for name in sorted(files):
        path = files[name]
        try:
            entry = AutostartEntry.from_file(path)
        except (OSError, UnicodeDecodeError, DesktopEntryError) as e:
            logger.warning("Skipping unparsable autostart entry %s: %s", path, e)
            continue
        if entry.should_autostart(desktops):
            entries.append(entry)
        else:
            logger.debug("Autostart entry %s filtered out", path)
    return entries


def launch_autostart_entry(entry: AutostartEntry) -> None:
    """Launch a single autostart entry."""
    try:
        args = entry.command()
    except DesktopEntryError as e:
        logger.warning("Cannot launch autostart entry %s: %s", entry.path, e)
        return

    if _parse_boolean(entry.keys.get("DBusActivatable", "false")):
        # We don't implement D-Bus activation; fall back to the Exec key,
        # which the specification requires for compatibility with
        # implementations that do not support D-Bus activation.
        logger.debug("Autostart entry %s is DBusActivatable; using Exec instead", entry.path)

    if _parse_boolean(entry.keys.get("Terminal", "false")):
        terminal = guess_terminal()
        if terminal is None:
            logger.warning(
                "Cannot launch autostart entry %s: it wants a terminal but none was found",
                entry.path,
            )
            return
        args = [terminal, "-e"] + args

    cwd = None
    path_key = entry.keys.get("Path")
    if path_key:
        cwd = _unescape_string(path_key)
        if not os.path.isdir(cwd):
            logger.warning(
                "Autostart entry %s has non-existent working directory %s", entry.path, cwd
            )
            cwd = None

    logger.info("Autostarting %s: %s", entry.name, args)
    try:
        subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        logger.warning("Failed to launch autostart entry %s: %s", entry.path, e)


def launch_autostart(
    directories: list[Path] | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """
    Launch all applications that should be autostarted, per the XDG
    autostart specification. This is done by qtile itself on first
    startup when the ``xdg_autostart`` config variable is set to True.
    """
    for entry in scan_autostart_entries(directories, env):
        launch_autostart_entry(entry)
