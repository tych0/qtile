import os

import pytest

import libqtile.bar
import libqtile.config
from libqtile.widget import df
from test.helpers import Retry


class FakeStatvfs:
    def __init__(self, *args, **kwargs):
        pass

    @property
    def f_frsize(self):
        return 4096

    @property
    def f_blocks(self):
        return 60000000

    @property
    def f_bfree(self):
        return 15000000

    @property
    def f_bavail(self):
        return 10000000


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_text(widget, text):
    assert widget.info()["text"] == text


# Patches os.statvfs gives these values for df widget:
#  unit: G
#  size = 228
#  free = 57
#  user_free = 38
#  ratio (user_free / size) = 83.3333%
@pytest.fixture
def df_manager(monkeypatch, manager_nospawn, minimal_conf_noscreen):
    def start(**kwargs):
        monkeypatch.setattr(os, "statvfs", FakeStatvfs)

        config = minimal_conf_noscreen
        config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([df.DF(**kwargs)], 10))]
        manager_nospawn.start(config)

        return manager_nospawn.c.widget["df"]

    return start


def test_df_no_warning(df_manager):
    """Test no text when free space over threshold"""
    widget = df_manager()
    wait_for_text(widget, "")

    widget.eval("self.draw()")
    assert widget.eval("self.layout.colour") == widget.eval("self.foreground")


def test_df_always_visible(df_manager):
    """Test text is always displayed"""
    widget = df_manager(visible_on_warn=False)

    # See values above
    wait_for_text(widget, "/ (38G|83%)")

    widget.eval("self.draw()")
    assert widget.eval("self.layout.colour") == widget.eval("self.foreground")


def test_df_warn_space(df_manager):
    """
    Test text is visible and colour changes when space
    below threshold
    """
    widget = df_manager(warn_space=40)

    # See values above
    wait_for_text(widget, "/ (38G|83%)")

    widget.eval("self.draw()")
    assert widget.eval("self.layout.colour") == widget.eval("self.warn_color")
