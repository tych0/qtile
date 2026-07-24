import sys
from importlib import reload
from types import ModuleType

import pytest

from libqtile.widget import gmail_checker
from test.widgets.conftest import wait_for_text


class FakeIMAP(ModuleType):
    class IMAP4_SSL:  # noqa: N801
        def __init__(self, *args, **kwargs):
            pass

        def login(self, username, password):
            self.username = username
            self.password = password

        def status(self, path, *args, **kwargs):
            if not (self.username and self.password):
                return False, None

            return ("OK", [f'("{path}" (MESSAGES 10 UNSEEN 2)'.encode()])


@pytest.fixture
def gmail_widget(monkeypatch, widget_manager):
    def start(**kwargs):
        monkeypatch.setitem(sys.modules, "imaplib", FakeIMAP("imaplib"))
        reload(gmail_checker)

        return widget_manager(gmail_checker.GmailChecker(**kwargs))

    return start


def test_gmail_checker_valid_response(gmail_widget):
    widget = gmail_widget(username="qtile", password="test")
    wait_for_text(widget, "inbox[10],unseen[2]")


def test_gmail_checker_invalid_response(gmail_widget):
    widget = gmail_widget()
    wait_for_text(widget, "UNKNOWN ERROR")


# This test is only required because the widget is written
# inefficiently. display_fmt should use keys instead of indices.
def test_gmail_checker_only_unseen(gmail_widget):
    widget = gmail_widget(
        display_fmt="unseen[{0}]", status_only_unseen=True, username="qtile", password="test"
    )
    wait_for_text(widget, "unseen[2]")
