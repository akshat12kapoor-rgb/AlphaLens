"""Indicator maths and the column contract the rest of the platform relies on."""
import pandas as pd
import pytest

from alphalens.signals import indicators

EXPECTED_COLUMNS = ["sma_20", "sma_50", "ema_20", "rsi", "macd", "macd_signal", "macd_diff"]


def test_enrich_adds_the_expected_columns(prices):
    enriched = indicators.enrich(prices)
    assert [c for c in EXPECTED_COLUMNS if c in enriched] == EXPECTED_COLUMNS


def test_enrich_does_not_mutate_its_input(prices):
    before = list(prices.columns)
    indicators.enrich(prices)
    assert list(prices.columns) == before


def test_sma_is_the_rolling_mean():
    series = pd.Series([1.0, 2, 3, 4, 5])
    assert indicators.sma(series, 2).tolist() == [1.0, 1.5, 2.5, 3.5, 4.5]


def test_rsi_stays_within_bounds(prices):
    values = indicators.rsi(prices["close"]).dropna()
    assert values.between(0, 100).all()


def test_rsi_is_high_when_prices_only_rise():
    rising = pd.Series(range(1, 60), dtype="float64")
    assert indicators.rsi(rising).iloc[-1] == pytest.approx(100.0)


def test_macd_histogram_is_line_minus_signal(prices):
    line, signal, histogram = indicators.macd(prices["close"])
    assert (line - signal - histogram).abs().max() < 1e-9
