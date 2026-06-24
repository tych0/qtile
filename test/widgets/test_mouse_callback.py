import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
from libqtile import widget
from libqtile.lazy import lazy
from test.conftest import MinimalConf


def lazy_callback_config():
    textbox = widget.TextBox(
        text="Testing",
        mouse_callbacks={
            "Button1": lazy.widget["textbox"].update("LazyCall"),
        },
    )

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([textbox], 10))]

    return Conf()


def test_lazy_callback(manager_nospawn):
    """Test widgets accept lazy calls"""
    manager_nospawn.start(lazy_callback_config)

    topbar = manager_nospawn.c.bar["top"]
    assert topbar.widget["textbox"].info()["text"] == "Testing"

    topbar.fake_button_press(0, 0, button=1)
    assert topbar.widget["textbox"].info()["text"] == "LazyCall"
