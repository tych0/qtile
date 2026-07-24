import sys
from importlib import reload
from types import ModuleType

import pytest

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

            return ("OK", [f'"{path}" (UNSEEN 2)'.encode()])

        def logout(self):
            pass


class FakeKeyring(ModuleType):
    valid = True

    def get_password(self, _app, user):
        if self.valid:
            return "password"
        return None


@pytest.fixture()
def patched_imap(monkeypatch):
    monkeypatch.delitem(sys.modules, "imaplib", raising=False)
    monkeypatch.delitem(sys.modules, "keyring", raising=False)
    monkeypatch.setitem(sys.modules, "imaplib", FakeIMAP("imaplib"))
    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring("keyring"))
    from libqtile.widget import imapwidget

    reload(imapwidget)
    yield imapwidget


@pytest.fixture
def imap_widget(widget_manager, patched_imap):
    def start(**kwargs):
        return widget_manager(patched_imap.ImapWidget(**kwargs))

    return start


def test_imapwidget(imap_widget):
    widget = imap_widget(user="qtile")
    wait_for_text(widget, "INBOX: 2")


def test_imapwidget_with_password(patched_imap, imap_widget):
    # keyring should not be called
    patched_imap.keyring.valid = False
    widget = imap_widget(user="qtile", password="password")
    wait_for_text(widget, "INBOX: 2")


def test_imapwidget_password_none(patched_imap, imap_widget):
    patched_imap.keyring.valid = False
    widget = imap_widget(user="qtile")
    wait_for_text(widget, "No password error")
