import sys
from importlib import reload
from types import ModuleType

import pytest

import libqtile.bar
import libqtile.config
from libqtile.widget import gmail_checker
from test.helpers import Retry


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


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_text(widget, text):
    assert widget.info()["text"] == text


@pytest.fixture
def gmail_manager(monkeypatch, manager_nospawn, minimal_conf_noscreen):
    def start(**kwargs):
        monkeypatch.setitem(sys.modules, "imaplib", FakeIMAP("imaplib"))
        reload(gmail_checker)

        config = minimal_conf_noscreen
        config.screens = [
            libqtile.config.Screen(
                top=libqtile.bar.Bar([gmail_checker.GmailChecker(**kwargs)], 10)
            )
        ]
        manager_nospawn.start(config)

        return manager_nospawn.c.widget["gmailchecker"]

    return start


def test_gmail_checker_valid_response(gmail_manager):
    widget = gmail_manager(username="qtile", password="test")
    wait_for_text(widget, "inbox[10],unseen[2]")


def test_gmail_checker_invalid_response(gmail_manager):
    widget = gmail_manager()
    wait_for_text(widget, "UNKNOWN ERROR")


# This test is only required because the widget is written
# inefficiently. display_fmt should use keys instead of indices.
def test_gmail_checker_only_unseen(gmail_manager):
    widget = gmail_manager(
        display_fmt="unseen[{0}]", status_only_unseen=True, username="qtile", password="test"
    )
    wait_for_text(widget, "unseen[2]")
