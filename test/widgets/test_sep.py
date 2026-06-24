import functools

import pytest

import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
from libqtile import widget
from test.conftest import MinimalConf


def orientations_config(location):
    sep = widget.Sep()
    if location == "top":
        screen = libqtile.config.Screen(top=libqtile.bar.Bar([sep], 10))
    else:
        screen = libqtile.config.Screen(left=libqtile.bar.Bar([sep], 10))

    class Conf(MinimalConf):
        screens = [screen]

    return Conf()


parameters = [
    ("top", "width"),
    ("left", "height"),
]


@pytest.mark.parametrize("location,attribute", parameters)
def test_orientations(manager_nospawn, location, attribute):
    manager_nospawn.start(functools.partial(orientations_config, location))
    bar = manager_nospawn.c.bar[location]

    w = bar.info()["widgets"][0]
    assert w[attribute] == 3


def padding_and_width_config():
    sep = widget.Sep(padding=5, linewidth=7)

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([sep], 10))]

    return Conf()


def test_padding_and_width(manager_nospawn):
    manager_nospawn.start(padding_and_width_config)
    topbar = manager_nospawn.c.bar["top"]

    w = topbar.info()["widgets"][0]
    assert w["width"] == 12


def test_deprecated_config():
    sep = widget.Sep(height_percent=80)
    assert sep.size_percent == 80
