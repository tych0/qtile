import libqtile.bar
import libqtile.config
from libqtile import widget
from test.helpers import Retry

RESPONSE = {"data": {"base": "BTC", "currency": "GBP", "amount": "29625.02"}}


@Retry(ignore_exceptions=(AssertionError,))
def wait_for_text(widget, text):
    assert widget.info()["text"] == text


async def fake_apoll(self):
    """Replaces the network request but still exercises the real parser."""
    return self.parse(RESPONSE)


def test_set_defaults():
    crypto = widget.CryptoTicker(currency="", symbol="")
    assert crypto.currency == "USD"
    assert crypto.symbol == "$"


def test_parse(monkeypatch, manager_nospawn, minimal_conf_noscreen):
    monkeypatch.setattr("libqtile.widget.crypto_ticker.CryptoTicker.apoll", fake_apoll)

    crypto = widget.CryptoTicker(currency="GBP", symbol="£", crypto="BTC")

    config = minimal_conf_noscreen
    config.screens = [libqtile.config.Screen(top=libqtile.bar.Bar([crypto], 10))]
    manager_nospawn.start(config)

    ticker = manager_nospawn.c.widget["cryptoticker"]
    assert ticker.eval("self.url") == "https://api.coinbase.com/v2/prices/BTC-GBP/spot"
    wait_for_text(ticker, "BTC: £29625.02")
