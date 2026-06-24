import pytest

import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
from libqtile.command.interface import CommandException
from libqtile.widget.crashme import _CrashMe
from test.conftest import MinimalConf


def crashme_config():
    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([_CrashMe()], 10))]

    return Conf()


def test_crashme_init(manager_nospawn):
    manager_nospawn.start(crashme_config)

    topbar = manager_nospawn.c.bar["top"]
    w = topbar.info()["widgets"][0]

    # Check that BadWidget has been replaced by ConfigErrorWidget
    assert w["name"] == "_crashme"
    assert w["text"] == "Crash me !"

    # Testing errors. Exceptions are wrapped in CommandException
    # so we catch that and match for the intended exception.

    # Left click generates ZeroDivisionError
    with pytest.raises(CommandException) as e_info:
        topbar.fake_button_press(0, 0, button=1)

    assert e_info.match("ZeroDivisionError")
