"""
Regression test for pytest-forked children inheriting unusable pango state.

Once the pytest process has rendered text (which lots of the widget tests
before this module do), pango's font map owns a helper thread that fork()
does not copy. A forked child that then loads a font the parent had not
cached deadlocks in g_cond_wait, unless it drops the inherited font map
first (see reset_pango_in_forked_children in test/conftest.py). Run alone,
before the pytest process has rendered anything, this passes vacuously.
"""

import pytest

from libqtile.widget import textbox
from test.widgets.conftest import FakeBar

pytestmark = [
    pytest.mark.forked,
    # see test/test_images.py: the isolation fork itself is fork-safe
    pytest.mark.filterwarnings("ignore:This process"),
]


def test_forked_child_draws_uncached_font(fake_qtile, fake_window):
    # an unusual font/size combination, to miss the parent's cache
    tb = textbox.TextBox(text="hello", font="DejaVu Serif", fontsize=37)
    fakebar = FakeBar([tb], window=fake_window)
    tb._configure(fake_qtile, fakebar)
    tb.draw()
