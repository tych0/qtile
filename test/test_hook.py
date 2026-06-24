import asyncio
import functools

import pytest

import libqtile.log_utils
import libqtile.utils
from libqtile import hook, layout
from libqtile.log_utils import logger
from libqtile.resources import default_config
from test.conftest import BareConfig, dualmonitor
from test.helpers import Retry


class Call:
    def __init__(self, val):
        self.val = val

    def __call__(self, val):
        self.val = val


class NoArgCall(Call):
    def __call__(self):
        self.val += 1


@pytest.fixture
def hook_fixture():
    libqtile.log_utils.init_log()
    yield
    hook.clear()


# The qtile child is launched in a forkserver process (see test/helpers.py), so
# it does not inherit any hook subscriptions made in the pytest parent. Tests
# that need a hook subscribed in the running qtile instead pass a *config
# builder* to start(): a module-level callable that runs in the child, builds a
# config, subscribes the hook there, and stashes the recording object on
# `config.test`. The parent reads the result back over IPC with
# `manager.c.eval("self.config.test.<attr>")`.


class Counter:
    """Hook handler that counts how many times it fires (ignoring any args)."""

    def __init__(self):
        self.count = 0

    def __call__(self, *args, **kwargs):
        self.count += 1


def build_hook_config(hook_name, call_factory=Counter, base=BareConfig):
    """Build a config that subscribes ``call_factory()`` to ``hook_name``.

    Runs in the forkserver child via ``start()``. The recording object is left
    on ``config.test`` so the parent can read it with ``manager.c.eval``.
    """
    config = base()
    config.test = call_factory()
    getattr(hook.subscribe, hook_name)(config.test)
    return config


@Retry(ignore_exceptions=(AssertionError))
def assert_count(mgr_nospawn, num):
    assert mgr_nospawn.c.eval("self.config.test.count") == str(num)


def test_cannot_fire_unknown_event():
    with pytest.raises(libqtile.utils.QtileError):
        hook.fire("unknown")


@pytest.mark.usefixtures("hook_fixture")
def test_hook_calls_subscriber():
    test = Call(0)
    hook.subscribe.group_window_add(test)
    hook.fire("group_window_add", 8)
    assert test.val == 8


@pytest.mark.usefixtures("hook_fixture")
def test_hook_calls_subscriber_async():
    val = 0

    async def co(new_val):
        nonlocal val
        val = new_val

    hook.subscribe.group_window_add(co)
    hook.fire("group_window_add", 8)

    assert val == 8


@pytest.mark.usefixtures("hook_fixture")
def test_hook_calls_subscriber_async_co():
    val = 0

    async def co(new_val):
        nonlocal val
        val = new_val

    hook.subscribe.group_window_add(co(8))
    hook.fire("group_window_add")

    assert val == 8


@pytest.mark.usefixtures("hook_fixture")
def test_hook_calls_subscriber_async_in_existing_loop():
    async def t():
        val = 0

        async def co(new_val):
            nonlocal val
            val = new_val

        hook.subscribe.group_window_add(co(8))
        hook.fire("group_window_add")
        await asyncio.sleep(0)
        assert val == 8

    asyncio.run(t())


@pytest.mark.usefixtures("hook_fixture")
def test_subscribers_can_be_added_removed():
    test = Call(0)
    hook.subscribe.group_window_add(test)
    assert hook.subscriptions
    hook.clear()
    assert not hook.subscriptions


@pytest.mark.usefixtures("hook_fixture")
def test_can_unsubscribe_from_hook():
    test = Call(0)

    hook.subscribe.group_window_add(test)
    hook.fire("group_window_add", 3)
    assert test.val == 3

    hook.unsubscribe.group_window_add(test)
    hook.fire("group_window_add", 4)
    assert test.val == 3


class StartupCounters:
    def __init__(self):
        self.once = 0
        self.startup = 0
        self.complete = 0


def build_startup_config():
    config = BareConfig()
    for attr in dir(default_config):
        if not hasattr(config, attr):
            setattr(config, attr, getattr(default_config, attr))
    config.test = StartupCounters()

    def inc(name):
        def _(*args, **kwargs):
            setattr(config.test, name, getattr(config.test, name) + 1)

        return _

    hook.subscribe.startup_once(inc("once"))
    hook.subscribe.startup(inc("startup"))
    hook.subscribe.startup_complete(inc("complete"))
    return config


def test_can_subscribe_to_startup_hooks(manager_nospawn):
    manager = manager_nospawn

    manager.start(build_startup_config)
    # The fresh child fired each startup hook exactly once.
    assert manager.c.eval("self.config.test.once") == "1"
    assert manager.c.eval("self.config.test.startup") == "1"
    assert manager.c.eval("self.config.test.complete") == "1"

    # Restart (a new child) and check that startup_once does NOT fire again,
    # while startup / startup_complete do. Each child counts independently, so
    # the restarted child reports once == 0 rather than a cumulative total.
    manager.terminate()
    manager.start(build_startup_config, no_spawn=True)
    assert manager.c.eval("self.config.test.once") == "0"
    assert manager.c.eval("self.config.test.startup") == "1"
    assert manager.c.eval("self.config.test.complete") == "1"


@pytest.mark.usefixtures("hook_fixture")
def test_can_update_by_selection_change(manager):
    test = Call(0)
    hook.subscribe.selection_change(test)
    hook.fire("selection_change", "hello")
    assert test.val == "hello"


@pytest.mark.usefixtures("hook_fixture")
def test_can_call_by_selection_notify(manager):
    test = Call(0)
    hook.subscribe.selection_notify(test)
    hook.fire("selection_notify", "hello")
    assert test.val == "hello"


@pytest.mark.usefixtures("hook_fixture")
def test_resume_hook(manager):
    test = NoArgCall(0)
    hook.subscribe.resume(test)
    hook.fire("resume")
    assert test.val == 1


@pytest.mark.usefixtures("hook_fixture")
def test_suspend_hook(manager):
    test = NoArgCall(0)
    hook.subscribe.suspend(test)
    hook.fire("suspend")
    assert test.val == 1


@pytest.mark.usefixtures("hook_fixture")
def test_custom_hook_registry():
    """Tests ability to create custom hook registries"""
    test = NoArgCall(0)

    custom = hook.Registry("test")
    custom.register_hook(hook.Hook("test_hook"))
    custom.subscribe.test_hook(test)

    assert test.val == 0

    # Test ability to fire third party hooks
    custom.fire("test_hook")
    assert test.val == 1

    # Check core hooks are not included in custom registry
    with pytest.raises(libqtile.utils.QtileError):
        custom.fire("client_managed")

    # Check custom hooks are not in core registry
    with pytest.raises(libqtile.utils.QtileError):
        hook.fire("test_hook")


class UserHookText:
    def __init__(self):
        self.no_arg_text = "A"
        self.text = "A"

    def set_text(self):
        self.no_arg_text = "B"

    def define_text(self, text):
        self.text = text


def build_user_hook_config():
    config = BareConfig()
    for attr in dir(default_config):
        if not hasattr(config, attr):
            setattr(config, attr, getattr(default_config, attr))
    config.test = UserHookText()
    hook.subscribe.user("set_text")(config.test.set_text)
    hook.subscribe.user("define_text")(config.test.define_text)
    return config


@pytest.mark.usefixtures("hook_fixture")
def test_user_hook(manager_nospawn):
    manager = manager_nospawn

    # Check values are as initialised
    manager.start(build_user_hook_config)
    assert manager.c.eval("self.config.test.no_arg_text") == "A"
    assert manager.c.eval("self.config.test.text") == "A"

    # Check hooked function with no args
    manager.c.fire_user_hook("set_text")
    assert manager.c.eval("self.config.test.no_arg_text") == "B"

    # Check hooked function with a single arg
    manager.c.fire_user_hook("define_text", "C")
    assert manager.c.eval("self.config.test.text") == "C"


def build_shutdown_config():
    config = BareConfig()

    def on_shutdown():
        logger.warning("shutdown hook fired")

    hook.subscribe.shutdown(on_shutdown)
    return config


def test_shutdown(manager_nospawn):
    manager_nospawn.start(build_shutdown_config)
    manager_nospawn.c.shutdown()

    # The shutdown hook fires as the child exits, so the IPC connection is gone;
    # read the confirmation back off the qtile log stream instead.
    @Retry(ignore_exceptions=(AssertionError))
    def assert_shutdown_logged():
        assert "shutdown hook fired" in manager_nospawn.get_log_buffer()

    assert_shutdown_logged()


@dualmonitor
def test_setgroup(manager_nospawn):
    # Starts with two because of the dual screen
    manager_nospawn.start(functools.partial(build_hook_config, "setgroup"))
    assert_count(manager_nospawn, 2)

    manager_nospawn.c.switch_groups("a", "b")
    assert_count(manager_nospawn, 3)

    manager_nospawn.c.to_screen(1)
    assert_count(manager_nospawn, 4)
    manager_nospawn.c.to_screen(1)
    assert_count(manager_nospawn, 4)

    manager_nospawn.c.next_screen()
    assert_count(manager_nospawn, 5)

    manager_nospawn.c.prev_screen()
    assert_count(manager_nospawn, 6)

    manager_nospawn.c.group.switch_groups("b")
    assert_count(manager_nospawn, 7)


class CallGroupname:
    def __init__(self):
        self.groupname = ""

    def __call__(self, groupname):
        self.groupname = groupname


@Retry(ignore_exceptions=(AssertionError))
def assert_groupname(mgr_nospawn, groupname):
    assert mgr_nospawn.c.eval("self.config.test.groupname") == groupname


@pytest.mark.usefixtures("hook_fixture")
def test_addgroup(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "addgroup", CallGroupname))
    assert_groupname(manager_nospawn, "d")
    manager_nospawn.c.addgroup("e")
    assert_groupname(manager_nospawn, "e")


@pytest.mark.usefixtures("hook_fixture")
def test_delgroup(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "delgroup", CallGroupname))
    manager_nospawn.c.delgroup("e")
    assert_groupname(manager_nospawn, "")
    manager_nospawn.c.delgroup("d")
    assert_groupname(manager_nospawn, "d")


def test_changegroup(manager_nospawn):
    # Starts with four beacuase of four groups in BareConfig
    manager_nospawn.start(functools.partial(build_hook_config, "changegroup"))
    assert_count(manager_nospawn, 4)

    manager_nospawn.c.group.set_label("Test")
    assert_count(manager_nospawn, 5)

    manager_nospawn.c.addgroup("e")
    assert_count(manager_nospawn, 6)
    manager_nospawn.c.addgroup("e")
    assert_count(manager_nospawn, 6)

    manager_nospawn.c.delgroup("e")
    assert_count(manager_nospawn, 7)
    manager_nospawn.c.delgroup("e")
    assert_count(manager_nospawn, 7)


def test_focus_change(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "focus_change"))
    assert_count(manager_nospawn, 1)

    manager_nospawn.test_window("Test Window")
    assert_count(manager_nospawn, 2)

    manager_nospawn.c.group.focus_by_index(0)
    assert_count(manager_nospawn, 3)
    manager_nospawn.c.group.focus_by_index(1)
    assert_count(manager_nospawn, 3)

    manager_nospawn.test_window("Test Focus Change")
    assert_count(manager_nospawn, 4)

    manager_nospawn.c.group.focus_back()
    assert_count(manager_nospawn, 5)

    manager_nospawn.c.group.focus_by_name("Test Focus Change")
    assert_count(manager_nospawn, 6)
    manager_nospawn.c.group.focus_by_name("Test Focus")
    assert_count(manager_nospawn, 6)

    manager_nospawn.c.group.next_window()
    assert_count(manager_nospawn, 7)

    manager_nospawn.c.group.prev_window()
    assert_count(manager_nospawn, 8)

    manager_nospawn.c.window.kill()
    assert_count(manager_nospawn, 9)


def test_float_change(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "float_change"))
    manager_nospawn.test_window("Test Window")

    manager_nospawn.c.window.enable_floating()
    assert_count(manager_nospawn, 1)
    manager_nospawn.c.window.enable_floating()
    assert_count(manager_nospawn, 1)

    manager_nospawn.c.window.disable_floating()
    assert_count(manager_nospawn, 2)
    manager_nospawn.c.window.disable_floating()
    assert_count(manager_nospawn, 2)

    manager_nospawn.c.window.toggle_floating()
    assert_count(manager_nospawn, 3)

    manager_nospawn.c.window.toggle_floating()
    manager_nospawn.c.window.move_floating(0, 0)
    assert_count(manager_nospawn, 5)

    manager_nospawn.c.window.toggle_floating()
    manager_nospawn.c.window.resize_floating(10, 10)
    assert_count(manager_nospawn, 7)

    manager_nospawn.c.window.toggle_floating()
    manager_nospawn.c.window.set_position_floating(0, 0)
    assert_count(manager_nospawn, 9)

    manager_nospawn.c.window.toggle_floating()
    manager_nospawn.c.window.set_size_floating(100, 100)
    assert_count(manager_nospawn, 11)


class CallGroupWindow:
    def __init__(self):
        self.window = ""
        self.group = ""

    def __call__(self, group, win):
        self.group = group.name
        self.window = win.name


@Retry(ignore_exceptions=(AssertionError))
def assert_group_window(mgr_nospawn, group, window):
    assert mgr_nospawn.c.eval("self.config.test.group") == group
    assert mgr_nospawn.c.eval("self.config.test.window") == window


@pytest.mark.usefixtures("hook_fixture")
def test_group_window_add(manager_nospawn):
    manager_nospawn.start(
        functools.partial(build_hook_config, "group_window_add", CallGroupWindow)
    )
    manager_nospawn.test_window("Test Window")
    assert_group_window(manager_nospawn, "a", "Test Window")


@pytest.mark.usefixtures("hook_fixture")
def test_group_window_remove(manager_nospawn):
    manager_nospawn.start(
        functools.partial(build_hook_config, "group_window_remove", CallGroupWindow)
    )
    manager_nospawn.test_window("Test Window")
    manager_nospawn.c.window.kill()
    assert_group_window(manager_nospawn, "a", "Test Window")


class CallWindow:
    def __init__(self):
        self.window = ""
        self.count = 0

    def __call__(self, window):
        self.window = window.name
        self.count += 1


@Retry(ignore_exceptions=(AssertionError))
def assert_window(mgr_nospawn, window):
    assert mgr_nospawn.c.eval("self.config.test.window") == window


@pytest.mark.usefixtures("hook_fixture")
def test_client_new(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "client_new", CallWindow))
    manager_nospawn.test_window("Test Client")
    assert_window(manager_nospawn, "Test Client")


@pytest.mark.usefixtures("hook_fixture")
def test_client_managed(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "client_managed", CallWindow))
    manager_nospawn.test_window("Test Client")
    assert_window(manager_nospawn, "Test Client")

    manager_nospawn.test_window("Test Static")
    manager_nospawn.c.group.focus_back()
    manager_nospawn.c.window.static()
    assert_window(manager_nospawn, "Test Client")


@pytest.mark.usefixtures("hook_fixture")
def test_client_killed(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "client_killed", CallWindow))
    manager_nospawn.test_window("Test Client")
    manager_nospawn.c.window.kill()
    assert_window(manager_nospawn, "Test Client")


@pytest.mark.usefixtures("hook_fixture")
def test_client_focus(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "client_focus", CallWindow))
    manager_nospawn.test_window("Test Client")
    assert_window(manager_nospawn, "Test Client")

    manager_nospawn.test_window("Test Focus")
    manager_nospawn.c.group.focus_back()
    assert_window(manager_nospawn, "Test Client")


@pytest.mark.usefixtures("hook_fixture")
def test_client_mouse_enter(manager_nospawn):
    manager_nospawn.start(
        functools.partial(build_hook_config, "client_mouse_enter", CallWindow)
    )
    manager_nospawn.test_window("Test Client")
    manager_nospawn.backend.fake_click(0, 0)
    assert_window(manager_nospawn, "Test Client")


@pytest.mark.usefixtures("hook_fixture")
def test_client_focus_by_click(manager_nospawn):
    manager_nospawn.start(
        functools.partial(build_hook_config, "client_focus_by_click", CallWindow)
    )
    manager_nospawn.test_window("Test Client")

    manager_nospawn.backend.fake_click(0, 0)
    assert manager_nospawn.c.eval("self.config.test.window") == "Test Client"
    assert manager_nospawn.c.eval("self.config.test.count") == "1"

    # Clicking on the window again will not fire the hook
    manager_nospawn.backend.fake_click(0, 0)
    assert manager_nospawn.c.eval("self.config.test.window") == "Test Client"
    assert manager_nospawn.c.eval("self.config.test.count") == "1"


@pytest.mark.usefixtures("hook_fixture")
def test_client_name_updated(manager_nospawn):
    manager_nospawn.start(
        functools.partial(build_hook_config, "client_name_updated", CallWindow)
    )
    manager_nospawn.test_window("Test Client", new_title="Test NameUpdated")
    assert_window(manager_nospawn, "Test NameUpdated")


@pytest.mark.usefixtures("hook_fixture")
def test_client_urgent_hint_changed(manager_nospawn):
    manager_nospawn.start(
        functools.partial(build_hook_config, "client_urgent_hint_changed", CallWindow)
    )
    manager_nospawn.test_window("Test Client", urgent=True)
    manager_nospawn.c.screen.next_group()
    assert_window(manager_nospawn, "Test Client")
    # Get urgency of the window
    assert manager_nospawn.c.eval("self.normal_windows()[0].urgent") == "True"
    # Refocusing the window should clear the urgency
    manager_nospawn.c.screen.prev_group()
    assert manager_nospawn.c.eval("self.normal_windows()[0].urgent") == "False"


class CallLayoutGroup:
    def __init__(self):
        self.layout = ""
        self.group = ""

    def __call__(self, layout, group):
        self.layout = layout.name
        self.group = group.name


class LayoutChangeConfig(BareConfig):
    layouts = [layout.stack.Stack(), layout.columns.Columns()]


@Retry(ignore_exceptions=(AssertionError))
def assert_layout_group(mgr_nospawn, layout, group):
    assert mgr_nospawn.c.eval("self.config.test.layout") == layout
    assert mgr_nospawn.c.eval("self.config.test.group") == group


@pytest.mark.usefixtures("hook_fixture")
def test_layout_change(manager_nospawn):
    manager_nospawn.start(
        functools.partial(build_hook_config, "layout_change", CallLayoutGroup, LayoutChangeConfig)
    )
    assert_layout_group(manager_nospawn, "stack", "a")

    manager_nospawn.c.group.setlayout("columns")
    assert_layout_group(manager_nospawn, "columns", "a")

    manager_nospawn.c.screen.next_group()
    assert_layout_group(manager_nospawn, "stack", "b")

    manager_nospawn.c.screen.prev_group()
    assert_layout_group(manager_nospawn, "columns", "a")

    manager_nospawn.c.screen.toggle_group()
    assert_layout_group(manager_nospawn, "stack", "b")

    manager_nospawn.c.next_layout()
    assert_layout_group(manager_nospawn, "columns", "b")

    manager_nospawn.c.prev_layout()
    assert_layout_group(manager_nospawn, "stack", "b")


@pytest.mark.usefixtures("hook_fixture")
def test_net_wm_icon_change(manager_nospawn, backend_name):
    if backend_name == "wayland":
        pytest.skip("X11 only.")

    manager_nospawn.start(
        functools.partial(build_hook_config, "net_wm_icon_change", CallWindow)
    )
    manager_nospawn.test_window("Test Client")
    assert_window(manager_nospawn, "Test Client")


@pytest.mark.usefixtures("hook_fixture")
def test_screen_change(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "screen_change"))
    assert_count(manager_nospawn, 1)


@pytest.mark.usefixtures("hook_fixture")
def test_screens_reconfigured(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "screens_reconfigured"))
    manager_nospawn.c.reconfigure_screens()
    assert_count(manager_nospawn, 1)


@dualmonitor
@pytest.mark.usefixtures("hook_fixture")
def test_current_screen_change(manager_nospawn):
    manager_nospawn.start(functools.partial(build_hook_config, "current_screen_change"))

    manager_nospawn.c.to_screen(1)
    assert_count(manager_nospawn, 1)
    manager_nospawn.c.to_screen(1)
    assert_count(manager_nospawn, 1)

    manager_nospawn.c.next_screen()
    assert_count(manager_nospawn, 2)

    manager_nospawn.c.prev_screen()
    assert_count(manager_nospawn, 3)


@pytest.mark.usefixtures("hook_fixture")
def test_transient_hooks_syncronous():
    def t_hook():
        return True

    def group_window(value):
        return value == 2

    hook.subscribe.startup(t_hook)
    assert len(hook.subscriptions["qtile"]["startup"]) == 1
    hook.fire("startup")
    assert len(hook.subscriptions["qtile"]["startup"]) == 0

    hook.subscribe.group_window_add(group_window)
    assert len(hook.subscriptions["qtile"]["group_window_add"]) == 1
    hook.fire("group_window_add", 1)
    assert len(hook.subscriptions["qtile"]["group_window_add"]) == 1
    hook.fire("group_window_add", 2)
    assert len(hook.subscriptions["qtile"]["group_window_add"]) == 0


@pytest.mark.usefixtures("hook_fixture")
def test_transient_hooks_asyncronous():
    async def t_hook():
        return True

    async def group_window(value):
        return value == 2

    hook.subscribe.startup(t_hook)
    assert len(hook.subscriptions["qtile"]["startup"]) == 1
    hook.fire("startup")
    assert len(hook.subscriptions["qtile"]["startup"]) == 0

    hook.subscribe.group_window_add(group_window)
    assert len(hook.subscriptions["qtile"]["group_window_add"]) == 1
    hook.fire("group_window_add", 1)
    assert len(hook.subscriptions["qtile"]["group_window_add"]) == 1
    hook.fire("group_window_add", 2)
    assert len(hook.subscriptions["qtile"]["group_window_add"]) == 0


@pytest.mark.usefixtures("hook_fixture")
def test_transient_hooks_coroutine():
    def len_hooks():
        return len(hook.subscriptions["qtile"]["startup"])

    async def wrapper():
        async def t_hook():
            return True

        hook.subscribe.startup(t_hook())
        assert len_hooks() == 1
        hook.fire("startup")

        # We need to cal asyncio.sleep to give the coroutine the
        # opportunity to run. The first sleep should be enough
        # but we add some extra loops to be safe.
        count = 0
        while count < 10:
            if len_hooks() == 0:
                break
            await asyncio.sleep(0.1)
            count += 1

        # We only get here if we haven't broken out of the loop
        else:
            assert False

        # Explicit confirmation that the hooks have been cleared
        assert len(hook.subscriptions["qtile"]["startup"]) == 0

    asyncio.run(wrapper())
