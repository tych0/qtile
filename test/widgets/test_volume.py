import pytest

from libqtile import images
from libqtile.widget import Volume
from test.helpers import Retry
from test.widgets.conftest import TEST_DIR, wait_for_eval


def test_images_fail():
    vol = Volume(theme_path=TEST_DIR)
    with pytest.raises(images.LoadingError):
        vol.setup_images()


def test_images_good(tmpdir, svg_img_as_pypath, widget_manager):
    names = (
        "audio-volume-high.svg",
        "audio-volume-low.svg",
        "audio-volume-medium.svg",
        "audio-volume-muted.svg",
    )
    for name in names:
        target = tmpdir.join(name)
        svg_img_as_pypath.copy(target)

    widget = widget_manager(Volume(theme_path=str(tmpdir), get_volume_command="echo '50%'"))

    @Retry(ignore_exceptions=(AssertionError,))
    def wait_for_images():
        assert widget.eval("len(self.images)") == str(len(names))

    wait_for_images()

    widget.eval(
        "import cairocffi\n"
        "self._test_result = True\n"
        "for image in self.images.values():\n"
        "    if not isinstance(image.pattern, cairocffi.SurfacePattern):\n"
        "        self._test_result = False"
    )
    assert widget.eval("self._test_result") == "True"


def test_emoji():
    vol = Volume(emoji=True)
    vol.volume = -1
    vol._update_drawer()
    assert vol.text == "\U0001f507"

    vol.volume = 29
    vol._update_drawer()
    assert vol.text == "\U0001f508"

    vol.volume = 79
    vol._update_drawer()
    assert vol.text == "\U0001f509"

    vol.volume = 80
    vol._update_drawer()
    assert vol.text == "\U0001f50a"

    vol.is_mute = True
    vol._update_drawer()
    assert vol.text == "\U0001f507"


def test_text():
    fmt = "Volume: {}"
    vol = Volume(fmt=fmt)
    vol.volume = -1
    vol._update_drawer()
    assert vol.text == "M"

    vol.volume = 50
    vol._update_drawer()
    assert vol.text == "50%"


def test_formats():
    unmute_format = "Volume: {volume}%"
    mute_format = "Volume: {volume}% M"
    vol = Volume(unmute_format=unmute_format, mute_format=mute_format)
    vol.volume = 50
    vol._update_drawer()
    assert vol.text == "Volume: 50%"

    vol.is_mute = True
    vol._update_drawer()
    assert vol.text == "Volume: 50% M"


def test_foregrounds(tmpdir, widget_manager):
    foreground = "#dddddd"
    mute_foreground = "#888888"

    # The widget's volume and mute state are read with real shell commands
    # whose output we control through these files.
    volume_file = tmpdir.join("volume")
    mute_file = tmpdir.join("mute")
    volume_file.write("50%")
    mute_file.write("[on]")

    vol = Volume(
        foreground=foreground,
        mute_foreground=None,
        get_volume_command=f"cat {volume_file}",
        check_mute_command=f"cat {mute_file}",
    )

    widget = widget_manager(vol)

    # Unmuted, no mute_foreground set: use foreground
    wait_for_eval(widget, "self.layout.colour", foreground)

    # Setting mute_foreground doesn't change the colour while unmuted
    widget.eval(f"self.mute_foreground = '{mute_foreground}'")
    wait_for_eval(widget, "self.layout.colour", foreground)

    # Muting the volume changes the colour to mute_foreground
    mute_file.write("[off]")
    wait_for_eval(widget, "self.layout.colour", mute_foreground)
