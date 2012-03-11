from .. import bar, manager
import base

class TextBox(base._TextBox):
    """
        A flexible textbox that can be updated from bound keys, scripts and
        qsh.
    """
    def __init__(self, name, text=" ", width=bar.CALCULATED, **config):
        """
            - name: Name for this widget. Used to address the widget from
            scripts, commands and qsh.
            - text: Initial widget text.
            - width: An integer width, bar.STRETCH, or bar.CALCULATED .
        """
        self.name = name
        base._TextBox.__init__(self, text, width, **config)
        self.load(config)

    def update(self, text):
        self.text = text
        self.bar.draw()

    def cmd_update(self, text):
        """
            Update the text in a TextBox widget.
        """
        self.update(text)

    def cmd_get(self):
        """
            Retrieve the text in a TextBox widget.
        """
        return self.text

