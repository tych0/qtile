import pickle
import shutil
import textwrap

import pytest

import libqtile.bar
import libqtile.config
import libqtile.layout
from libqtile import config, hook, layout
from libqtile.confreader import Config
from libqtile.ipc import IPCError
from libqtile.lazy import lazy
from libqtile.resources import default_config
from libqtile.widget import TextBox
from test.helpers import Retry
from test.helpers import TestManager as BareManager


class TwoScreenConfig(Config):
    auto_fullscreen = True
    groups = [config.Group("a"), config.Group("b"), config.Group("c"), config.Group("d")]
    layouts = [layout.stack.Stack(num_stacks=1), layout.stack.Stack(num_stacks=2)]
    floating_layout = default_config.floating_layout
    keys = [
        config.Key(
            ["control"],
            "k",
            lazy.layout.up(),
        ),
        config.Key(
            ["control"],
            "j",
            lazy.layout.down(),
        ),
    ]
    mouse = []
    follow_mouse_focus = False
    reconfigure_screens = False

    screens = []
    fake_screens = [
        libqtile.config.Screen(
            top=libqtile.bar.Bar([TextBox("Qtile Test")], 10), x=0, y=0, width=400, height=600
        ),
        libqtile.config.Screen(
            top=libqtile.bar.Bar([TextBox("Qtile Test")], 10), x=400, y=0, width=400, height=600
        ),
    ]


class RestartCounter:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1


def build_restart_config():
    """Subscribe a restart-hook counter inside the (forkserver) qtile child.

    The count is read back over IPC via ``self.config.test.count``.
    """
    config = TwoScreenConfig()
    config.test = RestartCounter()
    hook.subscribe.restart(config.test)
    return config


def test_restart_hook_and_state(manager_nospawn, request, backend, backend_name):
    if backend_name == "wayland":
        pytest.skip("Skipping test on Wayland.")

    manager = manager_nospawn

    # This injection allows us to capture the lifecycle state filepath before
    # restarting Qtile
    inject = textwrap.dedent(
        """
        from libqtile.core.lifecycle import lifecycle

        def no_op(*args, **kwargs):
            pass

        self.lifecycle = lifecycle
        self._do_stop = self._stop
        self._stop = no_op
        """
    )

    manager.start(build_restart_config)

    # Check that hook hasn't been fired yet.
    assert manager.c.eval("self.config.test.count") == "0"

    manager.c.group["c"].toscreen(0)
    manager.c.group["d"].toscreen(1)

    manager.test_window("one")
    manager.test_window("two")
    wins = {w["name"]: w["id"] for w in manager.c.windows()}
    manager.c.window[wins["one"]].togroup("c")
    manager.c.window[wins["two"]].togroup("d")

    # Inject the code and start the restart
    manager.c.eval(inject)
    manager.c.restart()

    # Check hook fired
    @Retry(ignore_exceptions=(AssertionError))
    def assert_restarted():
        assert manager.c.eval("self.config.test.count") == "1"

    assert_restarted()

    # Get the path to the state file
    state_file = manager.c.eval("self.lifecycle.state_file")
    assert state_file

    # We need a copy of this as the next file will probably overwrite it
    original_state = f"{state_file}-original"
    shutil.copy(state_file, original_state)

    # Stop the manager
    manager.c.eval("self._do_stop()")

    manager.proc.join(10)

    # Manager should have shutdown now so trying to access it will raise an error
    with pytest.raises((IPCError, ConnectionResetError)):
        assert manager.c.status()

    # Set up a new manager which takes our state file
    with BareManager(backend, request.config.getoption("--debuglog")) as restarted_manager:
        restarted_manager.start(TwoScreenConfig, state=state_file)

        # Test 1:
        # Check that groups are shown on correct screens
        screen0_info = restarted_manager.c.screen[0].group.info()
        assert screen0_info["name"] == "c"
        assert screen0_info["screen"] == 0

        screen1_info = restarted_manager.c.screen[1].group.info()
        assert screen1_info["name"] == "d"
        assert screen1_info["screen"] == 1

        # Test 2:
        # Check that clients are returned to the correct groups
        assert len(restarted_manager.c.windows()) == 2

        name_to_group = {w["name"]: w["group"] for w in restarted_manager.c.windows()}
        assert name_to_group["one"] == "c"
        assert name_to_group["two"] == "d"

        # Test 3:
        # Check that state file is the same

        # As before, inject code, restart and get state file
        restarted_manager.c.eval(inject)
        restarted_manager.c.restart()
        restarted_state = restarted_manager.c.eval("self.lifecycle.state_file")
        assert restarted_state
        restarted_manager.c.eval("self._do_stop()")

    # Load the two QtileState objects
    with open(original_state, "rb") as f:
        original = pickle.load(f)

    with open(restarted_state, "rb") as f:
        restarted = pickle.load(f)

    # Confirm that they're the same
    assert original.groups == restarted.groups
    assert original.screens == restarted.screens
    assert original.current_screen == restarted.current_screen
    assert original.scratchpads == restarted.scratchpads
