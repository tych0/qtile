import os
import time

import pytest

from libqtile.config import Key
from libqtile.extension.command_set import CommandSet
from libqtile.lazy import lazy
from test.helpers import Retry


# Fake dmenu process: the "selection" is the first item offered, unless the
# list of items starts with "missing" in which case something not in the
# list is returned.
class FakeDmenu:
    def __init__(self, *args, **kwargs):
        pass

    def communicate(self, value_in, *args):
        if value_in.startswith(b"missing"):
            return [b"something_else", None]
        return [value_in.split(b"\n")[0], None]


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_file(path):
    assert os.path.exists(str(path))


@pytest.fixture
def commandset_manager(monkeypatch, manager_nospawn, minimal_conf_noscreen):
    def start(extension):
        monkeypatch.setattr("libqtile.extension.base.Popen", FakeDmenu)

        config = minimal_conf_noscreen
        config.keys = [Key([], "a", lazy.run_extension(extension))]
        manager_nospawn.start(config)

        return manager_nospawn

    return start


def test_command_set_valid_command(tmpdir, commandset_manager):
    """Extension should run pre-commands and selected command."""
    pre = tmpdir.join("pre")
    cmd = tmpdir.join("cmd")

    extension = CommandSet(pre_commands=[f"touch {pre}"], commands={"key": f"touch {cmd}"})
    manager = commandset_manager(extension)

    manager.c.simulate_keypress([], "a")

    wait_for_file(pre)
    wait_for_file(cmd)


def test_command_set_invalid_command(tmpdir, commandset_manager):
    """Where the key is not in "commands", no command will be run."""
    pre = tmpdir.join("pre")
    cmd = tmpdir.join("cmd")

    extension = CommandSet(pre_commands=[f"touch {pre}"], commands={"missing": f"touch {cmd}"})
    manager = commandset_manager(extension)

    manager.c.simulate_keypress([], "a")

    wait_for_file(pre)
    time.sleep(0.5)
    assert not os.path.exists(str(cmd))


def test_command_set_inside_command_set_valid_command(tmpdir, commandset_manager):
    """Extension should run pre-commands and selected command."""
    pre = tmpdir.join("pre")
    inner_pre = tmpdir.join("inner_pre")
    cmd = tmpdir.join("cmd")

    inside_command = CommandSet(
        pre_commands=[f"touch {inner_pre}"],
        commands={"key": f"touch {cmd}"},
    )

    extension = CommandSet(
        pre_commands=[f"touch {pre}"],
        commands={"key": inside_command},
    )
    manager = commandset_manager(extension)

    manager.c.simulate_keypress([], "a")

    wait_for_file(pre)
    wait_for_file(inner_pre)
    wait_for_file(cmd)


def test_command_set_inside_command_set_invalid_command(tmpdir, commandset_manager):
    """Where the key is not in "commands", no command will be run."""
    pre = tmpdir.join("pre")
    inner_pre = tmpdir.join("inner_pre")
    cmd = tmpdir.join("cmd")

    inside_command = CommandSet(
        pre_commands=[f"touch {inner_pre}"],
        commands={"missing": f"touch {cmd}"},
    )

    extension = CommandSet(
        pre_commands=[f"touch {pre}"],
        commands={"key": inside_command},
    )
    manager = commandset_manager(extension)

    manager.c.simulate_keypress([], "a")

    # The outer and inner pre-commands run but the inner selection does not
    # match a command so nothing else is run
    wait_for_file(pre)
    wait_for_file(inner_pre)
    time.sleep(0.5)
    assert not os.path.exists(str(cmd))
