import libqtile.bar
import libqtile.config
from libqtile.widget import TextBox
from test.helpers import Retry


@Retry(ignore_exceptions=(AssertionError,), tmax=5)
def wait_for_widget(testbar, name):
    names = [w["name"] for w in testbar.info()["widgets"]]
    assert name in names, f"{name} not found in {names}"


@Retry(ignore_exceptions=(AssertionError,), tmax=5)
def wait_for_widget_gone(testbar, name):
    names = [w["name"] for w in testbar.info()["widgets"]]
    assert name not in names, f"{name} still present in {names}"


def test_check_logs_widget_injection(manager_nospawn, minimal_conf_noscreen):
    """The ``CheckLogs`` widget should be injectable into running bars by
    ``CheckLogs.inject_into_bars`` (which the ``_CheckLogsHandler`` calls
    whenever a warning-level log message is emitted), and clicking the
    widget should dismiss it."""
    config = minimal_conf_noscreen
    config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([TextBox("placeholder")], 24))]

    manager_nospawn.start(config)

    testbar = manager_nospawn.c.bar["top"]

    # Initially the widget should not be present.
    initial_widgets = [w["name"] for w in testbar.info()["widgets"]]
    assert "checklogs" not in initial_widgets

    # Trigger the same injection path that the logging handler would use.
    manager_nospawn.c.eval(
        "from libqtile.widget.check_logs import CheckLogs; CheckLogs.inject_into_bars(self)"
    )

    wait_for_widget(testbar, "checklogs")

    # Clicking the widget should dismiss it.
    widgets = testbar.info()["widgets"]
    cl = next(w for w in widgets if w["name"] == "checklogs")
    testbar.fake_button_press(cl["offset"], 0, button=1)
    wait_for_widget_gone(testbar, "checklogs")

    # A subsequent injection should re-add the widget.
    manager_nospawn.c.eval(
        "from libqtile.widget.check_logs import CheckLogs; CheckLogs.inject_into_bars(self)"
    )
    wait_for_widget(testbar, "checklogs")

    # Calling inject a second time while the widget is present must not
    # duplicate it.
    manager_nospawn.c.eval(
        "from libqtile.widget.check_logs import CheckLogs; CheckLogs.inject_into_bars(self)"
    )
    names = [w["name"] for w in testbar.info()["widgets"]]
    assert names.count("checklogs") == 1
