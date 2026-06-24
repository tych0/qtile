import functools

import pytest

import libqtile.bar
import libqtile.config
from libqtile.widget.base import _Widget
from test.conftest import MinimalConf


# This widget needs to crash during _configure
class BadWidget(_Widget):
    def _configure(self, qtile, bar):
        _Widget._configure(qtile, bar)
        1 / 0

    def draw(self):
        pass


def configerror_config(position):
    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(**{position: libqtile.bar.Bar([BadWidget(length=10)], 10)})]

    return Conf()


@pytest.mark.parametrize("position", ["top", "bottom", "left", "right"])
def test_configerrorwidget(manager_nospawn, position):
    """ConfigError widget should show in any bar orientation."""
    manager_nospawn.start(functools.partial(configerror_config, position))

    testbar = manager_nospawn.c.bar[position]
    w = testbar.info()["widgets"][0]

    # Check that BadWidget has been replaced by ConfigErrorWidget
    assert w["name"] == "configerrorwidget"
    assert w["text"] == "Widget crashed: BadWidget (click to hide)"

    # Clicking on widget hides it so let's check it works
    testbar.fake_button_press(0, 0, button=1)
    w = testbar.info()["widgets"][0]
    assert w["text"] == ""
