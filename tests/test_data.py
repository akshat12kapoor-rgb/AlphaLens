"""The data layer: CSV loading, Yahoo normalisation helpers, offline fixtures."""
import pandas as pd
import pytest

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


def test_install_serves_every_symbol_from_the_snapshot(monkeypatch):
    monkeypatch.setattr(yahoo, "prices", yahoo.prices)
    fixtures.install()
    assert yahoo.fundamentals("MSFT").symbol == "MSFT"
    assert len(yahoo.prices("ANYTHING")) == 500
    assert yahoo.news("ANYTHING")[0].title
    assert yahoo.quote("MSFT").currency == "USD"
