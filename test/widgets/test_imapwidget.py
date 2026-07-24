import sys
from importlib import reload
from types import ModuleType

import pytest

import libqtile.bar
import libqtile.config
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

            return ("OK", [f'"{path}" (UNSEEN 2)'.encode()])

        def logout(self):
            pass


class FakeKeyring(ModuleType):
    valid = True

    def get_password(self, _app, user):
        if self.valid:
            return "password"
        return None


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_text(widget, text):
    assert widget.info()["text"] == text


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
def imap_manager(manager_nospawn, minimal_conf_noscreen, patched_imap):
    def start(**kwargs):
        widget = patched_imap.ImapWidget(**kwargs)

        config = minimal_conf_noscreen
        config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([widget], 10))]
        manager_nospawn.start(config)

        return manager_nospawn.c.widget["imapwidget"]

    return start


def test_imapwidget(imap_manager):
    widget = imap_manager(user="qtile")
    wait_for_text(widget, "INBOX: 2")


def test_imapwidget_with_password(patched_imap, imap_manager):
    # keyring should not be called
    patched_imap.keyring.valid = False
    widget = imap_manager(user="qtile", password="password")
    wait_for_text(widget, "INBOX: 2")


def test_imapwidget_password_none(patched_imap, imap_manager):
    patched_imap.keyring.valid = False
    widget = imap_manager(user="qtile")
    wait_for_text(widget, "No password error")
