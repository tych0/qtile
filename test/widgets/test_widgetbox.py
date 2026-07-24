import pytest

import libqtile.config
from libqtile.widget import Systray, TextBox, WidgetBox


def test_widgetbox_widget(manager_nospawn, widget_manager):
    tb_one = TextBox(name="tb_one", text="TB ONE")
    tb_two = TextBox(name="tb_two", text="TB TWO")

    # Give widgetbox invalid value for button location
    widget_box = WidgetBox(widgets=[tb_one, tb_two], close_button_location="middle", fontsize=10)

    box = widget_manager(widget_box)
    topbar = manager_nospawn.c.bar["top"]

    def bar_widgets():
        return [w["name"] for w in topbar.info()["widgets"]]

    # Check only widget in bar is widgetbox
    assert bar_widgets() == ["widgetbox"]

    # Open box. The invalid close_button_location was corrected to the
    # default ("left") so the button is before its contents.
    box.toggle()
    assert bar_widgets() == ["widgetbox", "tb_one", "tb_two"]

    # Close box: widgets are removed
    box.toggle()
    assert bar_widgets() == ["widgetbox"]


def test_widgetbox_close_button_right(manager_nospawn, widget_manager):
    tb_one = TextBox(name="tb_one", text="TB ONE")
    tb_two = TextBox(name="tb_two", text="TB TWO")

    box = widget_manager(WidgetBox(widgets=[tb_one, tb_two], close_button_location="right"))

    box.toggle()

    # The widgetbox is on the right of its contents
    widgets = [w["name"] for w in manager_nospawn.c.bar["top"].info()["widgets"]]
    assert widgets == ["tb_one", "tb_two", "widgetbox"]


def test_widgetbox_start_opened(manager_nospawn, minimal_conf_noscreen):
    config = minimal_conf_noscreen
    tbox = TextBox(text="Text Box")
    widget_box = WidgetBox(widgets=[tbox], start_opened=True)
    config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([widget_box], 10))]

    manager_nospawn.start(config)

    topbar = manager_nospawn.c.bar["top"]
    widgets = [w["name"] for w in topbar.info()["widgets"]]
    assert widgets == ["widgetbox", "textbox"]


def test_widgetbox_mirror(manager_nospawn, minimal_conf_noscreen):
    config = minimal_conf_noscreen
    tbox = TextBox(text="Text Box")
    config.screens = [
        libqtile.config.Screen(top=libqtile.bar.Bar([tbox, WidgetBox(widgets=[tbox])], 10))
    ]

    manager_nospawn.start(config)

    manager_nospawn.c.widget["widgetbox"].toggle()
    topbar = manager_nospawn.c.bar["top"]
    widgets = [w["name"] for w in topbar.info()["widgets"]]
    assert widgets == ["textbox", "widgetbox", "mirror"]


def test_widgetbox_mouse_click(manager_nospawn, minimal_conf_noscreen):
    config = minimal_conf_noscreen
    tbox = TextBox(text="Text Box")
    config.screens = [
        libqtile.config.Screen(top=libqtile.bar.Bar([WidgetBox(widgets=[tbox])], 10))
    ]

    manager_nospawn.start(config)

    topbar = manager_nospawn.c.bar["top"]
    assert len(topbar.info()["widgets"]) == 1

    topbar.fake_button_press(0, 0, button=1)
    assert len(topbar.info()["widgets"]) == 2

    topbar.fake_button_press(0, 0, button=1)
    assert len(topbar.info()["widgets"]) == 1


def test_widgetbox_with_systray_reconfigure_screens_box_open(
    manager_nospawn, minimal_conf_noscreen, backend_name
):
    """Check that Systray does not crash when inside an open widgetbox."""
    if backend_name == "wayland":
        pytest.skip("Skipping test on Wayland.")

    config = minimal_conf_noscreen
    config.screens = [
        libqtile.config.Screen(top=libqtile.bar.Bar([WidgetBox(widgets=[Systray()])], 10))
    ]

    manager_nospawn.start(config)

    topbar = manager_nospawn.c.bar["top"]
    assert len(topbar.info()["widgets"]) == 1

    manager_nospawn.c.widget["widgetbox"].toggle()
    assert len(topbar.info()["widgets"]) == 2

    manager_nospawn.c.reconfigure_screens()

    assert len(topbar.info()["widgets"]) == 2
    names = [w["name"] for w in topbar.info()["widgets"]]
    assert names == ["widgetbox", "systray"]


def test_widgetbox_with_systray_reconfigure_screens_box_closed(
    manager_nospawn, minimal_conf_noscreen, backend_name
):
    """Check that Systray does not crash when inside a closed widgetbox."""
    if backend_name == "wayland":
        pytest.skip("Skipping test on Wayland.")

    config = minimal_conf_noscreen
    config.screens = [
        libqtile.config.Screen(top=libqtile.bar.Bar([WidgetBox(widgets=[Systray()])], 10))
    ]

    manager_nospawn.start(config)

    topbar = manager_nospawn.c.bar["top"]
    assert len(topbar.info()["widgets"]) == 1

    manager_nospawn.c.reconfigure_screens()

    assert len(topbar.info()["widgets"]) == 1

    # Check that we've still got a Systray widget in the box.
    assert manager_nospawn.c.widget["widgetbox"].eval("self.widgets[0].name") == "systray"


def test_deprecated_configuration(caplog):
    tray = Systray()
    box = WidgetBox([tray])
    assert box.widgets == [tray]
    assert "The use of a positional argument in WidgetBox is deprecated." in caplog.text


def test_widgetbox_open_close_commands(manager_nospawn, minimal_conf_noscreen):
    config = minimal_conf_noscreen
    tbox = TextBox(text="Text Box")
    widget_box = WidgetBox(widgets=[tbox])
    config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([widget_box], 10))]

    manager_nospawn.start(config)

    topbar = manager_nospawn.c.bar["top"]
    widget = manager_nospawn.c.widget["widgetbox"]

    def count():
        return len(topbar.info()["widgets"])

    assert count() == 1

    widget.open()
    assert count() == 2

    widget.open()
    assert count() == 2

    widget.close()
    assert count() == 1

    widget.close()
    assert count() == 1

    widget.toggle()
    assert count() == 2

    widget.toggle()
    assert count() == 1
