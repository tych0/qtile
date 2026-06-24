from functools import partial

import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
from libqtile.widget import CurrentLayout
from test.conftest import MinimalConf


def make_config(mode=None):
    kwargs = {} if mode is None else {"mode": mode}

    class Conf(MinimalConf):
        screens = [
            libqtile.config.Screen(top=libqtile.bar.Bar([CurrentLayout(**kwargs)], 10)),
        ]
        layouts = [
            libqtile.layout.Columns(),
            libqtile.layout.Max(),
            libqtile.layout.Stack(),
        ]

    return Conf()


def test_current_layout(manager_nospawn):
    manager_nospawn.start(make_config)
    widget = manager_nospawn.c.widget["currentlayout"]

    layout = widget.info()["text"]
    assert layout == "columns"

    manager_nospawn.c.next_layout()
    layout = widget.info()["text"]
    assert layout == "max"

    manager_nospawn.c.prev_layout()
    layout = widget.info()["text"]
    assert layout == "columns"

    widget.bar.fake_button_press(0, 0, button=1)
    layout = widget.info()["text"]
    assert layout == "max"

    widget.bar.fake_button_press(0, 0, button=2)
    layout = widget.info()["text"]
    assert layout == "columns"

    manager_nospawn.c.screen.next_group()
    manager_nospawn.c.to_layout_index(-1)
    layout = widget.info()["text"]
    assert layout == "stack"

    manager_nospawn.c.screen.prev_group()
    layout = widget.info()["text"]
    assert layout == "columns"


def test_current_layout_icon_mode(manager_nospawn):
    manager_nospawn.start(partial(make_config, mode="icon"))
    widget = manager_nospawn.c.widget["currentlayout"]
    img_length = int(widget.eval("self.img_length"))
    padding = int(widget.eval("self.padding"))
    text_length = int(widget.eval("super(type(self), self).calculate_length()"))

    length = int(widget.eval("self.length"))
    assert length == img_length + padding * 2

    widget.bar.fake_button_press(0, 0, button=3)
    length = int(widget.eval("self.length"))
    assert length == text_length

    widget.bar.fake_button_press(0, 0, button=3)
    length = int(widget.eval("self.length"))
    assert length == img_length + padding * 2


def test_current_layout_text_mode(manager_nospawn):
    manager_nospawn.start(partial(make_config, mode="text"))
    widget = manager_nospawn.c.widget["currentlayout"]
    img_length = int(widget.eval("self.img_length"))
    padding = int(widget.eval("self.padding"))
    text_length = int(widget.eval("super(type(self), self).calculate_length()"))

    length = int(widget.eval("self.length"))
    assert length == text_length

    widget.bar.fake_button_press(0, 0, button=3)
    length = int(widget.eval("self.length"))
    assert length == img_length + padding * 2

    widget.bar.fake_button_press(0, 0, button=3)
    length = int(widget.eval("self.length"))
    assert length == text_length


def test_current_layout_both_mode(manager_nospawn):
    manager_nospawn.start(partial(make_config, mode="both"))
    widget = manager_nospawn.c.widget["currentlayout"]
    img_length = int(widget.eval("self.img_length"))
    padding = int(widget.eval("self.padding"))
    text_length = int(widget.eval("super(type(self), self).calculate_length()"))

    length = int(widget.eval("self.length"))
    assert length == text_length + img_length + padding

    widget.bar.fake_button_press(0, 0, button=3)
    length = int(widget.eval("self.length"))
    assert length == text_length + img_length + padding
