import os
import shutil
import signal
import subprocess

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(TEST_DIR), "data")


@pytest.fixture(scope="module")
def svg_img_as_pypath():
    "Return the py.path object of a svg image"
    import py

    audio_volume_muted = os.path.join(
        DATA_DIR,
        "svg",
        "audio-volume-muted.svg",
    )
    audio_volume_muted = py.path.local(audio_volume_muted)
    return audio_volume_muted


@pytest.fixture(scope="function")
def dbus(monkeypatch):
    # for Github CI/Ubuntu, dbus-launch is provided by "dbus-x11" package
    launcher = shutil.which("dbus-launch")

    # If dbus-launch can't be found then tests will fail so we
    # need to skip
    if launcher is None:
        pytest.skip("dbus-launch must be installed")

    # dbus-launch prints two lines which should be set as
    # environmental variables
    result = subprocess.run(launcher, capture_output=True)

    pid = None
    for line in result.stdout.decode().splitlines():
        # dbus server addresses can have multiple "=" so
        # we use partition to split by the first one onle
        var, _, val = line.partition("=")

        # Use monkeypatch to set these variables so they are
        # removed at end of test.
        monkeypatch.setitem(os.environ, var, val)

        # We want the pid so we can kill the process when the
        # test is finished
        if var == "DBUS_SESSION_BUS_PID":
            try:
                pid = int(val)
            except ValueError:
                pass

    # Environment is set and dbus server should be running
    yield

    # Test is over so kill dbus session
    if pid:
        os.kill(pid, signal.SIGTERM)
