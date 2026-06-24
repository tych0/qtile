import libqtile.bar
import libqtile.config
import libqtile.confreader
import libqtile.layout
from libqtile.widget import CurrentScreen
from test.conftest import MinimalConf, dualmonitor

ACTIVE = "#FF0000"
INACTIVE = "#00FF00"


def currentscreen_config():
    class Conf(MinimalConf):
        screens = [
            libqtile.config.Screen(
                top=libqtile.bar.Bar(
                    [CurrentScreen(active_color=ACTIVE, inactive_color=INACTIVE)], 10
                )
            ),
            libqtile.config.Screen(),
        ]

    return Conf()


@dualmonitor
def test_change_screen(manager_nospawn):
    manager_nospawn.start(currentscreen_config)

    widget = manager_nospawn.c.widget["currentscreen"]

    assert widget.eval("self.text") == "A"
    assert widget.eval("self.layout.colour") == ACTIVE

    manager_nospawn.c.to_screen(1)

    assert widget.eval("self.text") == "I"
    assert widget.eval("self.layout.colour") == INACTIVE
