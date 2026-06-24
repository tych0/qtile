import functools

import pytest

from libqtile import widget
from libqtile.bar import Bar
from libqtile.config import Screen
from test.conftest import MinimalConf


def bad_importer(*args, **kwargs):
    raise ImportError()


def import_error_config(position):
    """Build the config in the forkserver child.

    The import is patched and the widget built here so the broken importer is
    in place in the qtile process that actually constructs the widget.
    """
    import libqtile.utils

    libqtile.utils.importlib.import_module = bad_importer

    badwidget = widget.TextBox("I am a naughty widget.")

    class ImportErrorConf(MinimalConf):
        screens = [Screen(**{position: Bar([badwidget], 10)})]

    return ImportErrorConf()


@pytest.mark.parametrize("position", ["top", "bottom", "left", "right"])
def test_importerrorwidget(manager_nospawn, position):
    """Check we get an ImportError widget with missing import?"""
    manager_nospawn.start(functools.partial(import_error_config, position))

    testbar = manager_nospawn.c.bar[position]
    w = testbar.info()["widgets"][0]

    # Check that the widget has been replaced with an ImportError
    assert w["name"] == "importerrorwidget"
    assert w["text"] == "Import Error: TextBox"
    assert len(w["missing_dependencies"]) > 1
    assert "libqtile" in w["missing_dependencies"]
