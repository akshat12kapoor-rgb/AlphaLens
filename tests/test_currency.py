"""Money is shown in the instrument's own currency, never a default one."""
import pytest

from alphalens.core import currency


@pytest.mark.parametrize("code, expected", [
    ("USD", "$"), ("INR", "₹"), ("EUR", "€"), ("JPY", "¥"), ("GBp", "p"),
])
def test_known_currencies_have_symbols(code, expected):
    assert currency.symbol_for(code) == expected


def test_unknown_currency_shows_its_code_rather_than_a_wrong_symbol():
    assert currency.symbol_for("PLN") == "PLN "


def test_missing_currency_falls_back_to_default():
    assert currency.symbol_for(None) == "$"


@pytest.mark.parametrize("symbol, expected", [
    ("RELIANCE.NS", "INR"), ("TCS.BO", "INR"), ("VOD.L", "GBp"),
    ("SAP.DE", "EUR"), ("7203.T", "JPY"), ("AAPL", "USD"), ("BTC-USD", "USD"),
])
def test_suffix_guess_used_only_as_a_fallback(symbol, expected):
    assert currency.guess_currency(symbol) == expected


def test_money_formats_in_the_given_currency():
    assert currency.money(1234.5, "INR") == "₹1,234.50"
    assert currency.money(1234.5, "USD") == "$1,234.50"
    assert currency.money(None, "USD") == "—"


def test_signed_money_marks_direction():
    assert currency.signed_money(1200, "INR") == "+₹1,200"
    assert currency.signed_money(-1200, "INR") == "−₹1,200"


@pytest.mark.parametrize("value, expected", [
    (416_160_000_000, "$416.16B"), (144_750_000_000, "$144.75B"),
    (5_400_000, "$5.40M"), (2_500_000_000_000, "$2.50T"), (940.5, "$940.50"),
])
def test_compact_money_scales(value, expected):
    assert currency.compact_money(value, "USD") == expected
