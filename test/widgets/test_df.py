import os

import pytest

from libqtile.widget import df
from test.widgets.conftest import wait_for_text

FOREGROUND = "#dddddd"
WARN_COLOR = "#ff0000"


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


# Patches os.statvfs gives these values for df widget:
#  unit: G
#  size = 228
#  free = 57
#  user_free = 38
#  ratio (user_free / size) = 83.3333%
@pytest.fixture
def df_widget(monkeypatch, widget_manager):
    def start(**kwargs):
        monkeypatch.setattr(os, "statvfs", FakeStatvfs)
        return widget_manager(df.DF(foreground=FOREGROUND, warn_color=WARN_COLOR, **kwargs))

    return start


def test_df_no_warning(df_widget):
    """Test no text when free space over threshold"""
    widget = df_widget()
    wait_for_text(widget, "")

    widget.eval("self.draw()")
    assert widget.eval("self.layout.colour") == FOREGROUND


def test_df_always_visible(df_widget):
    """Test text is always displayed"""
    widget = df_widget(visible_on_warn=False)

    # See values above
    wait_for_text(widget, "/ (38G|83%)")

    widget.eval("self.draw()")
    assert widget.eval("self.layout.colour") == FOREGROUND


def test_df_warn_space(df_widget):
    """
    Test text is visible and colour changes when space
    below threshold
    """
    widget = df_widget(warn_space=40)

    # See values above
    wait_for_text(widget, "/ (38G|83%)")

    widget.eval("self.draw()")
    assert widget.eval("self.layout.colour") == WARN_COLOR
