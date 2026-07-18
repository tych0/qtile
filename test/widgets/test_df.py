import pytest

from libqtile.widget import df
from test.widgets.conftest import FakeBar


class FakeStatvfs:
    """A fake return value for os.statvfs()"""

    def __init__(self, *args, **kwargs):
        pass

    f_frsize = 4096
    f_blocks = 60000000
    f_bfree = 15000000
    f_bavail = 10000000


# Patching os.statvfs gives these values for df widget:
#  unit: G
#  size = 228
#  free = 57
#  user_free = 38
#  ratio (user_free / size) = 83.3333%
@pytest.fixture()
def patched_df(monkeypatch):
    # Only patch the one function the widget uses. Replacing the whole os
    # module in sys.modules (as this fixture used to do) races against other
    # threads in the test process (e.g. pytest-xdist's execnet IO thread)
    # importing things while the fake, mostly-empty module is visible, which
    # occasionally deadlocked the worker.
    monkeypatch.setattr(df.os, "statvfs", FakeStatvfs)


@pytest.mark.usefixtures("patched_df")
def test_df_no_warning(fake_qtile, fake_window):
    """Test no text when free space over threshold"""
    df1 = df.DF()
    fakebar = FakeBar([df1], window=fake_window)
    df1._configure(fake_qtile, fakebar)
    text = df1.poll()
    assert text == ""

    df1.draw()
    assert df1.layout.colour == df1.foreground


@pytest.mark.usefixtures("patched_df")
def test_df_always_visible(fake_qtile, fake_window):
    """Test text is always displayed"""
    df2 = df.DF(visible_on_warn=False)
    fakebar = FakeBar([df2], window=fake_window)
    df2._configure(fake_qtile, fakebar)
    text = df2.poll()

    # See values above
    assert text == "/ (38G|83%)"

    df2.draw()
    assert df2.layout.colour == df2.foreground


@pytest.mark.usefixtures("patched_df")
def test_df_warn_space(fake_qtile, fake_window):
    """
    Test text is visible and colour changes when space
    below threshold
    """
    df3 = df.DF(warn_space=40)
    fakebar = FakeBar([df3], window=fake_window)
    df3._configure(fake_qtile, fakebar)
    text = df3.poll()

    # See values above
    assert text == "/ (38G|83%)"

    df3.draw()
    assert df3.layout.colour == df3.warn_color
