import sys
from importlib import reload
from types import ModuleType

import pytest

import libqtile.config
import libqtile.widget
from libqtile.bar import Bar
from test.conftest import MinimalConf


class MockPsutil(ModuleType):
    __version__ = "5.8.0"

    @classmethod
    def cpu_percent(cls):
        return 2.6

    @classmethod
    def cpu_freq(cls):
        class Freq:
            def __init__(self):
                self.current = 500.067
                self.min = 400.0
                self.max = 2800.0

        return Freq()


def cpu_config():
    """Build the CPU-widget config in the forkserver child.

    psutil is mocked and the widget is constructed here (not in the pytest
    parent) so the mock and the widget instance exist in the qtile process that
    actually polls them, rather than relying on fork() to carry them across.
    """
    sys.modules["psutil"] = MockPsutil("psutil")
    from libqtile.widget import cpu

    reload(cpu)

    class CPUConf(MinimalConf):
        screens = [libqtile.config.Screen(top=Bar([cpu.CPU()], 10))]

    return CPUConf()


@pytest.fixture
def cpu_manager(manager_nospawn):
    manager_nospawn.start(cpu_config)
    yield manager_nospawn


def test_cpu(cpu_manager):
    assert cpu_manager.c.widget["cpu"].info()["text"] == "CPU 0.5GHz 2.6%"
