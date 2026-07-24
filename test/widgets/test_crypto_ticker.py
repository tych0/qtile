from libqtile import widget
from test.widgets.conftest import wait_for_text

RESPONSE = {"data": {"base": "BTC", "currency": "GBP", "amount": "29625.02"}}


async def fake_apoll(self):
    """Replaces the network request but still exercises the real parser."""
    return self.parse(RESPONSE)


def test_set_defaults():
    crypto = widget.CryptoTicker(currency="", symbol="")
    assert crypto.currency == "USD"
    assert crypto.symbol == "$"


def test_parse(monkeypatch, widget_manager):
    monkeypatch.setattr("libqtile.widget.crypto_ticker.CryptoTicker.apoll", fake_apoll)

    ticker = widget_manager(widget.CryptoTicker(currency="GBP", symbol="£", crypto="BTC"))
    assert ticker.eval("self.url") == "https://api.coinbase.com/v2/prices/BTC-GBP/spot"
    wait_for_text(ticker, "BTC: £29625.02")
