import functools

import pytest

import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
import libqtile.widget as widgets
from libqtile.widget.base import ORIENTATION_BOTH, ORIENTATION_HORIZONTAL, ORIENTATION_VERTICAL
from libqtile.widget.clock import Clock
from libqtile.widget.crashme import _CrashMe
from test.conftest import MinimalConf
from test.widgets.conftest import FakeBar

# This file runs a very simple test to check that widgets can be initialised
# and that keyword arguments are added to default values.
#
# This test is not meant to replace any widget specific tests but should catch
# any mistakes that inadvertently breakag widgets.
#
# By default, the test runs on every widget that is listed in __init__.py
# This is done by building a list called `parameters` which contains a tuple of
# (widget class, kwargs).
#
# Adjustments to the tests can be made below.

# Some widgets may require certain parameters to be set when initialising.
# Widgets listed here will replace the default values.
# This should be used as a last resort - any failure may indicate an
# underlying issue in the widget that should be resolved.
overrides = []

# Some widgets are not included in __init__.py
# They can be included in the tests by adding their details here
extras = [
    (_CrashMe, {}),  # Just used by devs but no harm checking it works
]

# To skip a test entirely, list the widget class here
no_test = [widgets.Mirror, widgets.PulseVolume]  # Mirror requires a reflection object
no_test += [widgets.ImapWidget]  # Requires a configured username

# To test a widget only under one backend, list the widget class here
exclusive_backend = {
    widgets.Systray: "x11",
    widgets.Redshift: "x11",
    widgets.SwayNC: "wayland",
}

################################################################################
# Do not edit below this line
################################################################################

# Build default list of all widgets and assign simple keyword argument. Each
# entry also carries a picklable `key` that the forkserver child uses to
# re-resolve the widget class: widgets exposed via libqtile.widget are keyed by
# their attribute name (their import-error fallbacks are non-picklable closures
# that differ on every access, so the class object itself cannot be pickled);
# any other class (e.g. the extras) is picklable directly.
params_with_key = [(w, getattr(widgets, w), {"dummy_parameter": 1}) for w in widgets.__all__]

# Replace items in default list with overrides
for ovr in overrides:
    params_with_key = [(p[0], *ovr) if ovr[0] == p[1] else p for p in params_with_key]

# Add the extra widgets (keyed by the class itself, which is picklable)
params_with_key.extend((cls, cls, kwargs) for cls, kwargs in extras)

# Remove items which need to be skipped
for skipped in no_test:
    params_with_key = [p for p in params_with_key if p[1] != skipped]

# (widget_class, kwargs) tuples used for the parametrize ids and in-process checks
parameters = [(p[1], p[2]) for p in params_with_key]


def no_op(*args, **kwargs):
    pass


def _resolve_widget(key):
    """Resolve a picklable key (see params_with_key) back to a widget class."""
    if isinstance(key, str):
        return getattr(widgets, key)
    return key


def _widget_id(key):
    return key if isinstance(key, str) else key.__name__


def widget_config(key, kwargs, position):
    """Build a config (in the forkserver child) with a single widget in the bar."""
    widget = _resolve_widget(key)(**kwargs)
    widget.draw = no_op

    class Conf(MinimalConf):
        screens = [libqtile.config.Screen(**{position: libqtile.bar.Bar([widget], 10)})]

    return Conf()


@pytest.mark.parametrize(
    "key,kwargs",
    [
        (p[0], p[2])
        for p in params_with_key
        if p[1]().orientations in [ORIENTATION_BOTH, ORIENTATION_HORIZONTAL]
    ],
    ids=lambda val: _widget_id(val) if not isinstance(val, dict) else None,
)
def test_widget_init_config(manager_nospawn, key, kwargs):
    widget_class = _resolve_widget(key)
    if widget_class in exclusive_backend:
        if exclusive_backend[widget_class] != manager_nospawn.backend.name:
            pytest.skip("Unsupported backend")

    widget = widget_class(**kwargs)

    # If widget inits ok then kwargs will now be attributes
    for k, v in kwargs.items():
        assert getattr(widget, k) == v

    manager_nospawn.start(functools.partial(widget_config, key, kwargs, "top"))

    i = manager_nospawn.c.bar["top"].info()

    # Check widget is registered by checking names of widgets in bar
    assert i["widgets"][0]["name"] == widget.name


@pytest.mark.parametrize(
    "key,kwargs",
    [
        (p[0], p[2])
        for p in params_with_key
        if p[1]().orientations in [ORIENTATION_BOTH, ORIENTATION_VERTICAL]
    ],
    ids=lambda val: _widget_id(val) if not isinstance(val, dict) else None,
)
def test_widget_init_config_vertical_bar(manager_nospawn, key, kwargs):
    widget_class = _resolve_widget(key)
    if widget_class in exclusive_backend:
        if exclusive_backend[widget_class] != manager_nospawn.backend.name:
            pytest.skip("Unsupported backend")

    widget = widget_class(**kwargs)

    # If widget inits ok then kwargs will now be attributes
    for k, v in kwargs.items():
        assert getattr(widget, k) == v

    manager_nospawn.start(functools.partial(widget_config, key, kwargs, "left"))

    i = manager_nospawn.c.bar["left"].info()

    # Check widget is registered by checking names of widgets in bar
    assert i["widgets"][0]["name"] == widget.name


@pytest.mark.parametrize("widget_class,kwargs", parameters)
def test_widget_init_config_set_width(widget_class, kwargs):
    widget = widget_class(width=50)
    assert widget


def test_incompatible_orientation(fake_qtile, fake_window):
    clk1 = Clock()
    clk1.orientations = ORIENTATION_VERTICAL
    fakebar = FakeBar([clk1], window=fake_window)
    with pytest.raises(libqtile.confreader.ConfigError):
        clk1._configure(fake_qtile, fakebar)
