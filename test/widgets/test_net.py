import sys
from importlib import reload
from types import ModuleType

import pytest


# Net widget only needs bytes_recv/sent attributes
# Widget displays increase since last poll therefore
# we need to increment value each time this is called.
class MockPsutil(ModuleType):
    up = 0
    down = 0

    @classmethod
    def net_io_counters(cls, pernic=False, _nowrap=True):
        class IOCounters:
            def __init__(self, up, down):
                self.bytes_sent = up
                self.bytes_recv = down

        cls.up += 40000
        cls.down += 1200000

        if pernic:
            return {"wlp58s0": IOCounters(cls.up, cls.down), "lo": IOCounters(cls.up, cls.down)}
        return IOCounters(cls.up, cls.down)


# Patch the widget with our mock psutil module and run it in a real manager.
# Wrap the manager start so tests can pass keyword arguments to the widget.
@pytest.fixture
def net_widget(monkeypatch, widget_manager):
    def start(**kwargs):
        MockPsutil.up = 0
        MockPsutil.down = 0
        monkeypatch.setitem(sys.modules, "psutil", MockPsutil("psutil"))
        from libqtile.widget import net

        # Reload fixes cases where psutil may have been imported previously
        reload(net)
        return widget_manager(
            net.Net(
                format="{interface}: U {up}{up_suffix} {up_cumulative}{up_cumulative_suffix} D "
                "{down}{down_suffix} {down_cumulative}{down_cumulative_suffix} T {total}"
                "{total_suffix} {total_cumulative}{total_cumulative_suffix}",
                **kwargs,
            )
        )

    return start


def poll_text(widget):
    """Reset the mocked counters and poll the widget once.

    This is done in a single `eval` call so the widget's own timer cannot
    fire between the reset and the poll.
    """
    widget.eval(
        "import psutil\n"
        "type(psutil).up = 0\n"
        "type(psutil).down = 0\n"
        "self.stats = self.get_stats()\n"
        "self._test_text = self.poll()"
    )
    return widget.eval("self._test_text")


def test_net_defaults(net_widget):
    """Default: widget shows `all` interfaces"""
    assert poll_text(net_widget()) == "all: U 40.0kB 80.0kB D 1.2MB 2.4MB T 1.24MB 2.48MB"


def test_net_single_interface(net_widget):
    """Display single named interface"""
    assert (
        poll_text(net_widget(interface="wlp58s0"))
        == "wlp58s0: U 40.0kB 80.0kB D 1.2MB 2.4MB T 1.24MB 2.48MB"
    )


def test_net_list_interface(net_widget):
    """Display multiple named interfaces"""
    assert poll_text(net_widget(interface=["wlp58s0", "lo"])) == (
        "wlp58s0: U 40.0kB 80.0kB D 1.2MB 2.4MB T 1.24MB 2.48MB "
        "lo: U 40.0kB 80.0kB D 1.2MB 2.4MB T 1.24MB 2.48MB"
    )


def test_net_invalid_interface():
    """Pass an invalid interface value"""
    from libqtile.widget import net

    with pytest.raises(AttributeError):
        _ = net.Net(interface=12)


def test_net_use_bits(net_widget):
    """Display all interfaces in bits rather than bytes"""
    assert (
        poll_text(net_widget(use_bits=True))
        == "all: U 320.0kb 640.0kb D 9.6Mb 19.2Mb T 9.92Mb 19.84Mb"
    )


def test_net_convert_zero_b(net_widget):
    """Zero bytes is a special case in `convert_b`"""
    assert net_widget().eval("self.convert_b(0.0)") == "(0.0, 'B')"


def test_net_use_prefix(net_widget):
    """Tests `prefix` configurable option"""
    assert (
        poll_text(net_widget(prefix="M")) == "all: U 0.04MB 80.0kB D 1.2MB 2.4MB T 1.24MB 2.48MB"
    )


def test_net_missing_interface(net_widget):
    """Tests `missing_interface` option"""
    assert poll_text(net_widget(interface="unknown_interface")) == "unknown_interface not found"


def test_net_missing_interface_custom_string(net_widget):
    """Tests `missing_interface` option with custom string"""
    assert poll_text(net_widget(interface="unknown_interface", missing_interface="")) == ""


# Untested: 128-129 - generic exception catching
