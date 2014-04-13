from time import time
from datetime import datetime

import base
import warnings
import exceptions

class Clock(base.InLoopPollText):
    """
        A simple but flexible text-based clock.
    """
    defaults = [
        ('format', '%H:%M', 'A Python datetime format string'),

        # Here we override the default of 600 seconds, because we want the
        # clock to update whenever reasonable, not every 10 minutes :-)
        ('update_interval', None, 'Update interval for the clock'),
    ]
    def __init__(self, fmt=None, **config):
        base.InLoopPollText.__init__(self, **config)
        self.add_defaults(Clock.defaults)
        if fmt is not None:
            warnings.warn('fmt kwarg or positional argument is deprecated. '
                          'Please use format.', exceptions.DeprecationWarning)
            self.format = fmt

    def tick(self):
        ts = time()
        self.timeout_add(1. - ts % 1., self.tick)
        self.update(self.poll())
        return False

    def poll(self):
        ts = time()
        # adding .5 to get a proper seconds value because glib could
        # theoreticaly call our method too early and we could get something
        # like (x-1).999 instead of x.000
        return datetime.fromtimestamp(int(ts + .5)).strftime(self.format)
