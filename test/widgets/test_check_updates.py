import pytest

from libqtile.widget.check_updates import CheckUpdates
from test.widgets.conftest import wait_for_text

wrong_distro = "Barch"
good_distro = "Arch"
cmd_0_line = "export toto"  # quick "monkeypatch" simulating 0 output, ie 0 update
cmd_1_line = "echo toto"  # quick "monkeypatch" simulating 1 output, ie 1 update
cmd_error = "false"
nus = "No Update Available"


@pytest.fixture
def checkupdates_widget(monkeypatch, widget_manager):
    def start(widget=None, patches=None, **kwargs):
        if widget is None:
            widget = CheckUpdates(**kwargs)

        for target, value in (patches or {}).items():
            monkeypatch.setattr(target, value)

        return widget_manager(widget)

    return start


def test_unknown_distro():
    """test an unknown distribution"""
    cu = CheckUpdates(distro=wrong_distro)
    text = cu.poll()
    assert text == "N/A"


def test_update_available(checkupdates_widget):
    """test output with update (check number of updates and color)"""
    widget = checkupdates_widget(
        distro=good_distro, custom_command=cmd_1_line, colour_have_updates="#123456"
    )
    wait_for_text(widget, "Updates: 1")
    assert widget.eval("self.layout.colour") == "#123456"


def test_no_update_available_without_no_update_string(checkupdates_widget):
    """test output with no update (without dedicated string nor color)"""
    widget = checkupdates_widget(distro=good_distro, custom_command=cmd_0_line)
    wait_for_text(widget, "")


def test_no_update_available_with_no_update_string_and_color_no_updates(checkupdates_widget):
    """test output with no update (with dedicated string and color)"""
    widget = checkupdates_widget(
        distro=good_distro,
        custom_command=cmd_0_line,
        no_update_string=nus,
        colour_no_updates="#654321",
    )
    wait_for_text(widget, nus)
    assert widget.eval("self.layout.colour") == "#654321"


def test_update_available_with_restart_indicator(checkupdates_widget):
    """test output with an indicator where restart needed"""
    widget = checkupdates_widget(
        distro=good_distro,
        custom_command=cmd_1_line,
        restart_indicator="*",
    )

    # Patch os.path.exists inside a single `eval` call so the widget's own
    # timer never sees the patched version.
    widget.eval(
        "import os.path\n"
        "old_exists = os.path.exists\n"
        "os.path.exists = lambda x: True\n"
        "self._test_text = self.poll()\n"
        "os.path.exists = old_exists"
    )
    assert widget.eval("self._test_text") == "Updates: 1*"


def test_update_available_with_execute(checkupdates_widget, manager_nospawn):
    """test polling after executing command"""

    # Use monkeypatching to patch both Popen (for execute command) and call_process

    # This class returns None when first polled (to simulate that the task is still running)
    # and then 0 on the second call.
    class MockPopen:
        def __init__(self, *args, **kwargs):
            self.call_count = 0

        def poll(self):
            if self.call_count == 0:
                self.call_count += 1
                return None
            return 0

    # Bit of an ugly hack to replicate the above functionality but for a method.
    class MockSpawn:
        call_count = 0

        @classmethod
        def call_process(cls, *args, **kwargs):
            if cls.call_count == 0:
                cls.call_count += 1
                return "Updates"
            return ""

    cu6 = CheckUpdates(
        distro=good_distro,
        custom_command="dummy",
        execute="dummy",
        no_update_string=nus,
    )

    widget = checkupdates_widget(
        widget=cu6,
        patches={
            "libqtile.widget.check_updates.Popen": MockPopen,
            "libqtile.widget.check_updates.CheckUpdates.call_process": MockSpawn.call_process,
        },
    )

    wait_for_text(widget, "Updates: 1")

    # Clicking the widget triggers the execute command
    manager_nospawn.c.bar["top"].fake_button_press(0, 0, button=1)

    # The second time we poll the widget, the update process is complete
    # and there are no more updates
    widget.force_update()
    wait_for_text(widget, nus)


def test_update_process_error(checkupdates_widget):
    """test output where update check gives error"""
    widget = checkupdates_widget(
        distro=good_distro,
        custom_command=cmd_error,
        no_update_string="ERROR",
    )
    wait_for_text(widget, "ERROR")


def test_line_truncations(checkupdates_widget):
    """test update count is reduced"""

    # Mock output to return 5 lines of text
    def mock_process(*args, **kwargs):
        return "1\n2\n3\n4\n5\n"

    # Fedora is set up to remove 1 from line count
    cu8 = CheckUpdates(distro="Fedora")

    widget = checkupdates_widget(
        widget=cu8,
        patches={"libqtile.widget.check_updates.CheckUpdates.call_process": mock_process},
    )

    # Should have 4 updates
    wait_for_text(widget, "Updates: 4")
