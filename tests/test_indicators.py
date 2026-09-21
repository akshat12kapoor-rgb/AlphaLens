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


def test_ema_is_nan_during_warm_up():
    series = pd.Series(range(1, 30), dtype="float64")
    values = indicators.ema(series, 10)
    assert values.iloc[:9].isna().all()
    assert values.iloc[9:].notna().all()


def test_rsi_is_neutral_on_a_flat_series():
    flat = pd.Series([100.0] * 30)
    assert indicators.rsi(flat).iloc[-1] == pytest.approx(50.0)


def test_flat_window_marks_only_a_fully_flat_stretch():
    close = pd.Series([100.0] * 20 + [101.0] + [101.0] * 20)
    flat = indicators.flat_window(close, period=14)
    assert not flat.iloc[20]  # the jump bar itself
    assert not flat.iloc[25]  # window still spans the jump
    assert flat.iloc[-1]      # comfortably clear of the jump


def test_enrich_reads_a_flat_stretch_as_neutral_with_or_without_ta(monkeypatch):
    close = pd.Series([50.0] * 40)
    frame = pd.DataFrame({"close": close})

    with_ta = indicators.enrich(frame)
    monkeypatch.setattr(indicators, "TA_AVAILABLE", False)
    without_ta = indicators.enrich(frame)

    assert with_ta["rsi"].iloc[-1] == pytest.approx(50.0)
    assert without_ta["rsi"].iloc[-1] == pytest.approx(50.0)


def test_fallback_macd_has_no_crossovers_during_warm_up(monkeypatch):
    """Before `ema()` had `min_periods`, an under-converged EMA could fire a
    crossover purely from seeding transients while it was still warming up."""
    from alphalens.signals.strategies import HOLD, Context, _macd_events

    monkeypatch.setattr(indicators, "TA_AVAILABLE", False)
    close = pd.Series(range(1, 60), dtype="float64")
    frame = indicators.enrich(pd.DataFrame({"close": close}))

    warm_up = frame["macd"].isna() | frame["macd_signal"].isna()
    assert warm_up.any()
    events = _macd_events(frame, Context())
    assert (events[warm_up] == HOLD).all()
