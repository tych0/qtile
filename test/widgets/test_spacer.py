import functools

import pytest

import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
from libqtile import widget
from test.conftest import MinimalConf


def spacer_config(location, length=None):
    if length is None:
        space = widget.Spacer()
    else:
        space = widget.Spacer(length=length)
    if location == "top":
        screen = libqtile.config.Screen(top=libqtile.bar.Bar([space], 10))
    else:
        screen = libqtile.config.Screen(left=libqtile.bar.Bar([space], 10))

    class Conf(MinimalConf):
        screens = [screen]

    return Conf()


parameters = [
    ("top", "width"),
    ("left", "height"),
]


@pytest.mark.parametrize("location,attribute", parameters)
def test_stretch(manager_nospawn, location, attribute):
    manager_nospawn.start(functools.partial(spacer_config, location))
    bar = manager_nospawn.c.bar[location]

    info = bar.info()
    assert info["widgets"][0][attribute] == info[attribute]


@pytest.mark.parametrize("location,attribute", parameters)
def test_fixed_size(manager_nospawn, location, attribute):
    manager_nospawn.start(functools.partial(spacer_config, location, 100))
    bar = manager_nospawn.c.bar[location]

    info = bar.info()
    assert info["widgets"][0][attribute] == 100
