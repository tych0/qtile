import functools
from os import path

import pytest

import libqtile.bar
import libqtile.config
from libqtile import widget
from test.conftest import MinimalConf

TEST_DIR = path.dirname(path.abspath(__file__))
DATA_DIR = path.join(TEST_DIR, "..", "data", "png")
IMAGE_FILE = path.join(DATA_DIR, "audio-volume-muted.png")


def image_config(filename, location):
    img = widget.Image(filename=filename)
    bar = libqtile.bar.Bar([img], 40)

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(**{location: bar})]

    return Conf()


parameters = [
    (IMAGE_FILE, "top", "height"),
    (IMAGE_FILE, "left", "width"),
]


@pytest.mark.parametrize("filename,location,attribute", parameters)
def test_default_settings(manager_nospawn, filename, location, attribute):
    manager_nospawn.start(functools.partial(image_config, filename, location))
    bar = manager_nospawn.c.bar[location]

    info = bar.info()
    for dimension in ["height", "width"]:
        assert info["widgets"][0][dimension] == info[attribute]


parameters = [
    (None, "top", "width"),
    (None, "left", "height"),
]


@pytest.mark.parametrize("filename,location,attribute", parameters)
def test_no_filename(manager_nospawn, filename, location, attribute):
    manager_nospawn.start(functools.partial(image_config, filename, location))
    bar = manager_nospawn.c.bar[location]

    info = bar.info()
    assert info["widgets"][0][attribute] == 0


def missing_file_config():
    img2 = widget.Image(filename="/this/file/does/not/exist")

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([img2], 40))]

    return Conf()


def test_missing_file(manager_nospawn):
    manager_nospawn.start(missing_file_config)
    bar = manager_nospawn.c.bar["top"]

    info = bar.info()
    assert info["widgets"][0]["width"] == 0


def no_scale_config():
    img2 = widget.Image(filename=IMAGE_FILE, scale=False)

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([img2], 40))]

    return Conf()


def test_no_scale(manager_nospawn):
    manager_nospawn.start(no_scale_config)
    bar = manager_nospawn.c.bar["top"]

    info = bar.info()
    assert info["widgets"][0]["width"] == 24


def no_image_config():
    img = widget.Image()

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([img], 40))]

    return Conf()


def test_no_image(manager_nospawn):
    manager_nospawn.start(no_image_config)

    assert "Image filename not set!" in manager_nospawn.get_log_buffer()


def invalid_path_config():
    img = widget.Image(filename="/made/up/file.png")

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(top=libqtile.bar.Bar([img], 40))]

    return Conf()


def test_invalid_path(manager_nospawn):
    filename = "/made/up/file.png"

    manager_nospawn.start(invalid_path_config)

    assert f"Image does not exist: {filename}" in manager_nospawn.get_log_buffer()
