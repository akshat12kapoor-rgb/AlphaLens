"""The data layer: CSV loading, Yahoo normalisation helpers, offline fixtures."""
import time

import pandas as pd
import pytest

from alphalens.data import cache as cache_module
from alphalens.data import csv_prices, fixtures, yahoo
from alphalens.data.models import DataUnavailable, Fundamentals, MissingData

CSV = """Date,Open,High,Low,Close,Volume
2024-01-03,10,11,9,10.5,1000
2024-01-02,9,10,8,9.5,900
"""


def write(tmp_path, text, name="prices.csv"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_csv_is_sorted_by_date_and_renamed(tmp_path):
    frame, symbol = csv_prices.load_prices(write(tmp_path, CSV))
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.is_monotonic_increasing
    assert symbol == "PRICES"


def test_missing_columns_are_named(tmp_path):
    with pytest.raises(DataUnavailable, match="High, Low"):
        csv_prices.load_prices(write(tmp_path, "Date,Open,Close,Volume\n2024-01-01,1,1,1\n"))


def test_duplicate_dates_are_rejected(tmp_path):
    duplicated = CSV + "2024-01-02,9,10,8,9.5,900\n"
    with pytest.raises(DataUnavailable, match="duplicate date"):
        csv_prices.load_prices(write(tmp_path, duplicated))


def test_bad_dates_are_reported_with_a_row_number(tmp_path):
    with pytest.raises(DataUnavailable, match="row 2"):
        csv_prices.load_prices(write(tmp_path, "Date,Open,High,Low,Close,Volume\nnope,1,1,1,1,1\n"))


def test_zero_volume_rows_are_dropped_like_yahoo_prices(tmp_path):
    csv = CSV + "2024-01-04,10.5,11,10,10.8,0\n"
    frame, _ = csv_prices.load_prices(write(tmp_path, csv))
    assert len(frame) == 2
    assert (frame["volume"] > 0).all()


def test_an_all_zero_volume_csv_is_rejected(tmp_path):
    csv = "Date,Open,High,Low,Close,Volume\n2024-01-01,1,1,1,1,0\n"
    with pytest.raises(DataUnavailable, match="nonzero volume"):
        csv_prices.load_prices(write(tmp_path, csv))


def test_sample_prices_ship_with_the_platform():
    frame, symbol = csv_prices.sample_prices()
    assert symbol == "SAMPLE"
    assert len(frame) == 400


# ── Yahoo normalisation (no network) ────────────────────────────────────────

def statement(rows: dict) -> pd.DataFrame:
    """A statement frame shaped like Yahoo's: one row per line item, one column
    per period end, newest first."""
    columns = pd.to_datetime(["2024-12-31", "2023-12-31"])
    return pd.DataFrame.from_dict(rows, orient="index", columns=columns).astype("float64")


def test_statement_rows_are_returned_oldest_first_by_year():
    frame = statement({"Total Revenue": [200.0, 100.0]})
    series = yahoo._row(frame, ["Total Revenue"])
    assert list(series.index) == ["2023", "2024"]
    assert list(series) == [100.0, 200.0]


def test_statement_rows_try_each_alias():
    frame = statement({"Operating Revenue": [200.0, 100.0]})
    assert not yahoo._row(frame, ["Total Revenue", "Operating Revenue"]).empty
    assert yahoo._row(frame, ["Nothing Named This"]).empty


def test_free_cash_flow_prefers_the_reported_row():
    frame = statement({"Free Cash Flow": [50.0, 40.0]})
    assert list(yahoo._free_cash_flow(frame)) == [40.0, 50.0]


def test_free_cash_flow_falls_back_to_operating_less_capex():
    frame = statement({"Operating Cash Flow": [100.0, 90.0],
                       "Capital Expenditure": [-30.0, -20.0]})
    # Capex is reported negative, so the spend is subtracted.
    assert list(yahoo._free_cash_flow(frame)) == [70.0, 70.0]


def test_missing_statements_give_empty_series():
    assert yahoo._free_cash_flow(pd.DataFrame()).empty
    assert yahoo._latest(pd.Series(dtype="float64")) is None


def test_fundamentals_rescale_statements_to_match_the_quote_currency(monkeypatch):
    """LSE-style tickers quote in pence (GBp) but report statements in pounds
    (GBP). `price` and the statement figures must end up in the same unit."""
    info = {
        "currency": "GBp",
        "financialCurrency": "GBP",
        "currentPrice": 500.0,
        "trailingEps": 45.0,
        "totalRevenue": 1_000_000.0,
        "freeCashflow": 200_000.0,
        "ebitda": 300_000.0,
        "netIncomeToCommon": 150_000.0,
        "totalDebt": 50_000.0,
        "totalCash": 20_000.0,
        "sharesOutstanding": 1_000.0,
        "longName": "Test PLC",
    }
    empty_stock = type("Stock", (), {"income_stmt": pd.DataFrame(), "cashflow": pd.DataFrame(),
                                     "balance_sheet": pd.DataFrame()})()
    monkeypatch.setattr(yahoo, "_info", lambda symbol: info)
    monkeypatch.setattr(yahoo, "_ticker", lambda symbol: empty_stock)

    data = yahoo.fundamentals.__wrapped__("TEST.L")

    assert data.currency == "GBp"
    assert data.price == 500.0
    assert data.eps == 45.0  # already in the quote currency, never rescaled
    assert data.revenue == pytest.approx(1_000_000.0 * 100)
    assert data.free_cash_flow == pytest.approx(200_000.0 * 100)
    assert data.ebitda == pytest.approx(300_000.0 * 100)
    assert data.net_income == pytest.approx(150_000.0 * 100)
    assert data.total_debt == pytest.approx(50_000.0 * 100)
    assert data.cash == pytest.approx(20_000.0 * 100)


def test_fundamentals_do_not_rescale_when_currencies_already_match(monkeypatch):
    info = {"currency": "USD", "financialCurrency": "USD", "currentPrice": 100.0,
            "totalRevenue": 500.0, "sharesOutstanding": 10.0}
    empty_stock = type("Stock", (), {"income_stmt": pd.DataFrame(), "cashflow": pd.DataFrame(),
                                     "balance_sheet": pd.DataFrame()})()
    monkeypatch.setattr(yahoo, "_info", lambda symbol: info)
    monkeypatch.setattr(yahoo, "_ticker", lambda symbol: empty_stock)

    data = yahoo.fundamentals.__wrapped__("TEST")

    assert data.currency == "USD"
    assert data.revenue == 500.0


# ── network resilience (retry + negative cache) ─────────────────────────────

def test_with_retry_recovers_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return "ok"

    assert yahoo._with_retry(flaky, attempts=3, base_delay=0) == "ok"
    assert calls["n"] == 3


def test_with_retry_raises_the_last_failure_once_exhausted():
    def always_fails():
        raise ConnectionError("still down")

    with pytest.raises(ConnectionError, match="still down"):
        yahoo._with_retry(always_fails, attempts=2, base_delay=0)


def test_negative_cache_short_circuits_until_the_cooldown_expires():
    calls = {"n": 0}

    @cache_module.negative_cache(ttl=0.05)
    def flaky(symbol):
        calls["n"] += 1
        raise DataUnavailable("down")

    with pytest.raises(DataUnavailable):
        flaky("NEGATIVE_CACHE_TEST")
    assert calls["n"] == 1

    # Immediately again: still within the cooldown, must not retry the network.
    with pytest.raises(DataUnavailable):
        flaky("NEGATIVE_CACHE_TEST")
    assert calls["n"] == 1

    time.sleep(0.06)
    with pytest.raises(DataUnavailable):
        flaky("NEGATIVE_CACHE_TEST")
    assert calls["n"] == 2


def test_periods_are_limited_per_interval():
    assert "10y" in yahoo.periods_for("1d")
    assert yahoo.periods_for("5m") == ["5d", "1mo"]
    assert yahoo.periods_for("unknown") == ["3mo", "6mo", "1y"]


# ── fixtures ────────────────────────────────────────────────────────────────

def test_fixture_prices_look_like_market_data(prices):
    assert list(prices.columns) == ["open", "high", "low", "close", "volume"]
    assert len(prices) == 500
    assert (prices["high"] >= prices["low"]).all()


def test_fixture_fundamentals_are_complete_enough_to_value(fundamentals):
    assert fundamentals.symbol == "AAPL"
    assert fundamentals.currency == "USD"
    fundamentals.require("free_cash_flow", "shares_outstanding", "price")


def test_missing_fields_are_named_in_the_error():
    empty = Fundamentals(symbol="X", name="X", currency="USD")
    with pytest.raises(MissingData, match="free cash flow, shares outstanding"):
        empty.require("free_cash_flow", "shares_outstanding")


def test_a_genuinely_zero_field_is_not_reported_as_missing():
    """A break-even company has free cash flow - it's just 0.0, not absent."""
    breakeven = Fundamentals(symbol="X", name="X", currency="USD", free_cash_flow=0.0,
                             shares_outstanding=10.0)
    breakeven.require("free_cash_flow", "shares_outstanding")  # must not raise


def test_install_serves_every_symbol_from_the_snapshot(monkeypatch):
    monkeypatch.setattr(yahoo, "prices", yahoo.prices)
    fixtures.install()
    assert yahoo.fundamentals("MSFT").symbol == "MSFT"
    assert len(yahoo.prices("ANYTHING")) == 500
    assert yahoo.news("ANYTHING")[0].title
    assert yahoo.quote("MSFT").currency == "USD"
