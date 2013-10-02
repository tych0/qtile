# This is mostly just a hack to avoid stuff like:
#   from libqtile.widget.prompt import Prompt

from backlight import Backlight
from battery import Battery, BatteryIcon
from clock import Clock
from currentlayout import CurrentLayout
from graph import CPUGraph, MemoryGraph, SwapGraph, NetGraph, HDDGraph, HDDBusyGraph
from groupbox import AGroupBox, GroupBox
from maildir import Maildir
from notify import Notify
from pacman import Pacman
from prompt import Prompt
from sensors import ThermalSensor
from sep import Sep
from she import She
from spacer import Spacer
from systray import Systray
from tasklist import TaskList
from textbox import TextBox
from volume import Volume
from windowname import WindowName
from windowtabs import WindowTabs
from keyboardlayout import KeyboardLayout
from df import DF
from image import Image


# We use lazy_import to warn people when they are missing dependencies. If your
# widget has extra dependencies that are not listed in
# /docs/manual/install/source.rst then you should use this wrapper.
def lazy_import(module, widget):
    def fake(*args, **kwargs):
        try:
            m = __import__(module, fromlist=module)
            cls = getattr(m, widget)
            return cls(*args, **kwargs)
        except ImportError as e:
            return TextBox(e.message)
    return fake


Canto = lazy_import("canto", "Canto")
Mpris = lazy_import("mpriswidget", "Mpris")
Mpd = lazy_import("mpdwidget", "Mpd")
YahooWeather = lazy_import("yahoo_weather", "YahooWeather")
BitcoinTicker = lazy_import("bitcoin_ticker", "BitcoinTicker")
Wlan = lazy_import("wlan", "Wlan")
GoogleCalendar = lazy_import("google_calendar", "GoogleCalendar")
