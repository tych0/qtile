import textwrap
import time
from pathlib import Path

import pytest

from libqtile import xdg_autostart


def make_entry(directory, name, content):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(textwrap.dedent(content))
    return path


def simple_entry(exec_line="true", **keys):
    extra = "".join(f"{k}={v}\n" for k, v in keys.items())
    return f"""\
        [Desktop Entry]
        Type=Application
        Name=Test
        Exec={exec_line}
        {extra}"""


def test_parse_desktop_file(tmp_path):
    path = make_entry(
        tmp_path,
        "test.desktop",
        """\
        # A comment
        [Desktop Entry]
        Type=Application
        Name=My App
        Exec=myapp --flag

        [Desktop Action Other]
        Name=Something else
        """,
    )
    keys = xdg_autostart.parse_desktop_file(path)
    assert keys["Type"] == "Application"
    assert keys["Name"] == "My App"
    assert keys["Exec"] == "myapp --flag"
    # Keys from other groups are not included.
    assert len(keys) == 3


def test_parse_desktop_file_errors(tmp_path):
    path = make_entry(tmp_path, "nogroup.desktop", "Type=Application\n")
    with pytest.raises(xdg_autostart.DesktopEntryError):
        xdg_autostart.parse_desktop_file(path)

    path = make_entry(tmp_path, "badline.desktop", "[Desktop Entry]\nnot a key value pair\n")
    with pytest.raises(xdg_autostart.DesktopEntryError):
        xdg_autostart.parse_desktop_file(path)


def test_unescape_string():
    assert xdg_autostart._unescape_string(r"a\sb\nc\td\re\\f") == "a b\nc\td\re\\f"
    # Unknown escapes are left alone.
    assert xdg_autostart._unescape_string(r"a\;b") == r"a\;b"


def test_parse_string_list():
    assert xdg_autostart._parse_string_list("GNOME;KDE;") == ["GNOME", "KDE"]
    assert xdg_autostart._parse_string_list("GNOME;KDE") == ["GNOME", "KDE"]
    assert xdg_autostart._parse_string_list(r"a\;b;c;") == ["a;b", "c"]
    assert xdg_autostart._parse_string_list("") == []


def test_parse_exec_quoting():
    assert xdg_autostart.parse_exec("myapp --flag arg") == ["myapp", "--flag", "arg"]
    assert xdg_autostart.parse_exec('myapp "an arg"') == ["myapp", "an arg"]
    assert xdg_autostart.parse_exec('myapp "a \\"quoted\\" arg"') == ["myapp", 'a "quoted" arg']
    assert xdg_autostart.parse_exec('myapp ""') == ["myapp", ""]
    assert xdg_autostart.parse_exec("  myapp   arg  ") == ["myapp", "arg"]
    with pytest.raises(xdg_autostart.DesktopEntryError):
        xdg_autostart.parse_exec('myapp "unterminated')


def test_command_field_codes(tmp_path):
    path = make_entry(
        tmp_path,
        "codes.desktop",
        simple_entry(exec_line="myapp %U --pct %% %i --name %c --file %k", Icon="myicon"),
    )
    entry = xdg_autostart.AutostartEntry.from_file(path)
    assert entry.command() == [
        "myapp",
        "--pct",
        "%",
        "--icon",
        "myicon",
        "--name",
        "Test",
        "--file",
        str(path),
    ]


def test_command_no_exec(tmp_path):
    path = make_entry(tmp_path, "noexec.desktop", "[Desktop Entry]\nType=Application\n")
    entry = xdg_autostart.AutostartEntry.from_file(path)
    with pytest.raises(xdg_autostart.DesktopEntryError):
        entry.command()


@pytest.mark.parametrize(
    "keys,desktops,expected",
    [
        ({}, ["qtile"], True),
        ({"Hidden": "true"}, ["qtile"], False),
        ({"Hidden": "false"}, ["qtile"], True),
        ({"OnlyShowIn": "GNOME;"}, ["qtile"], False),
        ({"OnlyShowIn": "GNOME;qtile;"}, ["qtile"], True),
        ({"NotShowIn": "qtile;"}, ["qtile"], False),
        ({"NotShowIn": "KDE;"}, ["qtile"], True),
        ({"OnlyShowIn": "X-Custom;"}, ["X-Custom", "qtile"], True),
        ({"Type": "Link"}, ["qtile"], False),
        ({"TryExec": "/nonexistent/binary"}, ["qtile"], False),
        ({"TryExec": "sh"}, ["qtile"], True),
    ],
)
def test_should_autostart(tmp_path, keys, desktops, expected):
    path = make_entry(tmp_path, "test.desktop", simple_entry(**keys))
    entry = xdg_autostart.AutostartEntry.from_file(path)
    assert entry.should_autostart(desktops) is expected


def test_autostart_directories():
    env = {"XDG_CONFIG_HOME": "/home/test/.config", "XDG_CONFIG_DIRS": "/etc/xdg:/usr/etc/xdg"}
    assert xdg_autostart.autostart_directories(env) == [
        Path("/home/test/.config/autostart"),
        Path("/etc/xdg/autostart"),
        Path("/usr/etc/xdg/autostart"),
    ]

    env = {"HOME": "/home/test"}
    assert xdg_autostart.autostart_directories(env) == [
        Path("~/.config/autostart").expanduser(),
        Path("/etc/xdg/autostart"),
    ]


def test_scan_precedence_and_hidden(tmp_path):
    user_dir = tmp_path / "user"
    system_dir = tmp_path / "system"
    # The same ID in both directories: the user's copy wins, and since it
    # is Hidden, the entry is disabled entirely.
    make_entry(user_dir, "masked.desktop", simple_entry(Hidden="true"))
    make_entry(system_dir, "masked.desktop", simple_entry())
    # An entry only in the system directory.
    make_entry(system_dir, "system.desktop", simple_entry())
    # An entry overridden by the user with a different Exec.
    make_entry(user_dir, "both.desktop", simple_entry(exec_line="user-version"))
    make_entry(system_dir, "both.desktop", simple_entry(exec_line="system-version"))
    # Non-desktop files are ignored.
    make_entry(user_dir, "README.txt", "not a desktop file")

    entries = xdg_autostart.scan_autostart_entries([user_dir, system_dir], env={})
    by_name = {e.path.name: e for e in entries}
    assert sorted(by_name) == ["both.desktop", "system.desktop"]
    assert by_name["both.desktop"].command() == ["user-version"]


def test_scan_respects_current_desktop(tmp_path):
    make_entry(tmp_path, "gnome-only.desktop", simple_entry(OnlyShowIn="GNOME;"))
    make_entry(tmp_path, "not-qtile.desktop", simple_entry(NotShowIn="qtile;"))
    make_entry(tmp_path, "everywhere.desktop", simple_entry())

    entries = xdg_autostart.scan_autostart_entries([tmp_path], env={})
    assert [e.path.name for e in entries] == ["everywhere.desktop"]

    entries = xdg_autostart.scan_autostart_entries(
        [tmp_path], env={"XDG_CURRENT_DESKTOP": "GNOME"}
    )
    assert [e.path.name for e in entries] == [
        "everywhere.desktop",
        "gnome-only.desktop",
        "not-qtile.desktop",
    ]


def test_scan_skips_unparsable(tmp_path):
    make_entry(tmp_path, "broken.desktop", "no group header here\n")
    make_entry(tmp_path, "good.desktop", simple_entry())
    entries = xdg_autostart.scan_autostart_entries([tmp_path], env={})
    assert [e.path.name for e in entries] == ["good.desktop"]


def test_launch_autostart_runs_command(tmp_path):
    stamp = tmp_path / "stamp"
    make_entry(
        tmp_path / "autostart",
        "touch.desktop",
        simple_entry(exec_line=f"touch {stamp}"),
    )
    make_entry(
        tmp_path / "autostart",
        "hidden.desktop",
        simple_entry(exec_line=f"touch {tmp_path}/hidden-stamp", Hidden="true"),
    )
    xdg_autostart.launch_autostart([tmp_path / "autostart"], env={})
    for _ in range(100):
        if stamp.exists():
            break
        time.sleep(0.1)
    assert stamp.exists()
    assert not (tmp_path / "hidden-stamp").exists()


def test_launch_autostart_bad_working_directory(tmp_path):
    stamp = tmp_path / "stamp"
    make_entry(
        tmp_path / "autostart",
        "badpath.desktop",
        simple_entry(exec_line=f"touch {stamp}", Path="/nonexistent/directory"),
    )
    xdg_autostart.launch_autostart([tmp_path / "autostart"], env={})
    for _ in range(100):
        if stamp.exists():
            break
        time.sleep(0.1)
    assert stamp.exists()
