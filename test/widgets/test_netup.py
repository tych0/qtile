import pytest

from libqtile.widget import NetUP
from test.widgets.conftest import wait_for_eval, wait_for_text

UP_FOREGROUND = "00ff00"
DOWN_FOREGROUND = "ff0000"


@pytest.fixture
def netup_widget(monkeypatch, widget_manager):
    def start(patch_target, patch_value, **kwargs):
        monkeypatch.setattr(patch_target, patch_value)
        return widget_manager(
            NetUP(
                up_string="UP",
                down_string="DOWN",
                up_foreground=UP_FOREGROUND,
                down_foreground=DOWN_FOREGROUND,
                **kwargs,
            )
        )

    return start


def test_host_is_empty():
    netup = NetUP()
    assert netup.poll() == "N/A"


def test_invalid_method():
    netup = NetUP(host="localhost", method="icmp")
    assert netup.poll() == "N/A"


def test_invalid_port():
    netup = NetUP(host="localhost", method="tcp", port="port")
    assert netup.poll() == "N/A"


def mock_ping_success(*args, **kwargs):
    class MockResult:
        returncode = 0

    return MockResult()


def mock_ping_fail(*args, **kwargs):
    class MockResult:
        returncode = 1

    return MockResult()


def test_ping_success(netup_widget):
    widget = netup_widget(
        "libqtile.widget.netup.run", mock_ping_success, host="localhost", method="ping"
    )

    wait_for_text(widget, "NET UP")
    wait_for_eval(widget, "self.layout.colour", UP_FOREGROUND)


def test_ping_fail(netup_widget):
    widget = netup_widget(
        "libqtile.widget.netup.run", mock_ping_fail, host="localhost", method="ping"
    )

    wait_for_text(widget, "NET DOWN")
    wait_for_eval(widget, "self.layout.colour", DOWN_FOREGROUND)


def test_tcp_success(netup_widget):
    widget = netup_widget(
        "libqtile.widget.netup.NetUP.check_tcp",
        lambda *args, **kwargs: 0,
        host="localhost",
        method="tcp",
        port=443,
    )

    wait_for_text(widget, "NET UP")
    wait_for_eval(widget, "self.layout.colour", UP_FOREGROUND)


def test_tcp_fail(netup_widget):
    widget = netup_widget(
        "libqtile.widget.netup.NetUP.check_tcp",
        lambda *args, **kwargs: -1,
        host="localhost",
        method="tcp",
        port=443,
    )

    wait_for_text(widget, "NET DOWN")
    wait_for_eval(widget, "self.layout.colour", DOWN_FOREGROUND)
