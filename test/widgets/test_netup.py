import pytest

import libqtile.bar
import libqtile.config
from libqtile.widget import NetUP
from test.helpers import Retry


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_text(widget, text):
    assert widget.info()["text"] == text


@pytest.fixture
def netup_manager(monkeypatch, manager_nospawn, minimal_conf_noscreen):
    def start(patch_target, patch_value, **kwargs):
        monkeypatch.setattr(patch_target, patch_value)

        config = minimal_conf_noscreen
        config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([NetUP(**kwargs)], 10))]
        manager_nospawn.start(config)

        return manager_nospawn.c.widget["netup"]

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


def test_ping_success(netup_manager):
    widget = netup_manager(
        "libqtile.widget.netup.run", mock_ping_success, host="localhost", method="ping"
    )

    wait_for_text(widget, "NET " + widget.eval("self.up_string"))
    assert widget.eval("self.layout.colour") == widget.eval("self.up_foreground")


def test_ping_fail(netup_manager):
    widget = netup_manager(
        "libqtile.widget.netup.run", mock_ping_fail, host="localhost", method="ping"
    )

    wait_for_text(widget, "NET " + widget.eval("self.down_string"))
    assert widget.eval("self.layout.colour") == widget.eval("self.down_foreground")


def test_tcp_success(netup_manager):
    widget = netup_manager(
        "libqtile.widget.netup.NetUP.check_tcp",
        lambda *args, **kwargs: 0,
        host="localhost",
        method="tcp",
        port=443,
    )

    wait_for_text(widget, "NET " + widget.eval("self.up_string"))
    assert widget.eval("self.layout.colour") == widget.eval("self.up_foreground")


def test_tcp_fail(netup_manager):
    widget = netup_manager(
        "libqtile.widget.netup.NetUP.check_tcp",
        lambda *args, **kwargs: -1,
        host="localhost",
        method="tcp",
        port=443,
    )

    wait_for_text(widget, "NET " + widget.eval("self.down_string"))
    assert widget.eval("self.layout.colour") == widget.eval("self.down_foreground")
