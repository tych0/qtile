import datetime
from .. import bar, manager
import base


class Clock(base._TextBox):
    """
        A simple but flexible text-based clock.
    """
    def __init__(self, fmt="%H:%M", width=bar.CALCULATED, **config):
        """
            - fmt: A Python datetime format string.

            - width: A fixed width, or bar.CALCULATED to calculate the width
            automatically (which is recommended).
        """
        base._TextBox.__init__(self, " ", width, **config)
        self.fmt = fmt
        self.timeout_add(1, self.update)

    def _configure(self, qtile, bar):
        base._TextBox._configure(self, qtile, bar)

    def update(self):
        if self.configured:
            now = datetime.datetime.now().strftime(self.fmt)
            if self.text != now:
                self.text = now
                self.bar.draw()
        return True
