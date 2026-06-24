import functools

import pytest

import libqtile.bar
import libqtile.config
from libqtile import widget
from test.conftest import MinimalConf


def textbox_config(position):
    textbox = widget.TextBox(text="Testing")

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(**{position: libqtile.bar.Bar([textbox], 10)})]

    return Conf()


@pytest.mark.parametrize("position", ["top", "bottom", "left", "right"])
def test_text_box_bar_orientations(manager_nospawn, position):
    """Text boxes are available on any bar position."""
    manager_nospawn.start(functools.partial(textbox_config, position))
    tbox = manager_nospawn.c.widget["textbox"]

    assert tbox.info()["text"] == "Testing"

    tbox.update("Updated")
    assert tbox.info()["text"] == "Updated"


def max_chars_config():
    textbox = widget.TextBox(text="Testing", max_chars=4)

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([textbox], 10))]

    return Conf()


def test_text_box_max_chars(manager_nospawn):
    """Text boxes are available on any bar position."""
    manager_nospawn.start(max_chars_config)
    tbox = manager_nospawn.c.widget["textbox"]

    assert tbox.info()["text"] == "Test…"
