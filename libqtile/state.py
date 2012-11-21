# Copyright (c) 2012, Tycho Andersen. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from collections import defaultdict

import command
import hook

class GroupState(object):
    def __init__(self, group):
        self.name = group.name
        self.layout = group.currentLayout
        self.windows = [w.wid for w in group.windows]

class QtileState(object):
    def __init__(self, qtile):
        self.groups = [GroupState(g) for g in qtile.groups]

    def apply(self, qtile):
        """
            Rearrange the windows in the specified Qtile object according to
            this QtileState.
        """
        def windows():
            for g in self.groups:
                for w in g.windows:
                    yield g, w

        # First, dgroups (or some other user process) could have created some
        # groups. We fire the client_new hook on every window to alert any
        # hooks that the windows exist (and create any groups or other state
        # for them).
        for _, w in windows():
            try:
                hook.fire("client_new", qtile.windowMap[w])
            except KeyError:
                pass

        # Now, the automatic catigorization may have put windows in their
        # default place, but users may have moved them. Additionally, windows
        # in static groups haven't been assigned a home yet. So, we move them
        # to wherever they were.
        for g, w in windows():
            try:
                qtile.windowMap[w].togroup(g.name)
            except (KeyError, command.CommandError):
                pass # CommandError => group doesn't exist, not possible (?)

        for g in self.groups:
            try:
                qtile.groupMap[g.name].layout = g.layout
            except KeyError:
                pass

        # TODO: restore which group each screen has, which => layoutAll()
