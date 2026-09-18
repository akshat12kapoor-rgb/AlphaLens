"""Fair Value Gap and liquidity sweep detection."""
import pandas as pd

from alphalens.signals import smc


def frame(rows):
    return pd.DataFrame(rows, index=pd.date_range("2024-01-01", periods=len(rows), freq="D"))


def test_bullish_gap_detected_when_candle_three_clears_candle_one():
    gaps = smc.fair_value_gaps(frame([
        {"open": 10, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1},
        {"open": 10.3, "high": 12.0, "low": 10.2, "close": 11.9, "volume": 1},
        {"open": 11.5, "high": 12.5, "low": 11.0, "close": 12.2, "volume": 1},
    ]))
    assert len(gaps) == 1
    assert gaps.iloc[0]["type"] == "bullish"
    assert gaps.iloc[0]["bottom"] == 10.5  # candle 1 high
    assert gaps.iloc[0]["top"] == 11.0     # candle 3 low


def test_bearish_gap_is_the_mirror_image():
    gaps = smc.fair_value_gaps(frame([
        {"open": 12, "high": 12.5, "low": 11.5, "close": 11.8, "volume": 1},
        {"open": 11.4, "high": 11.5, "low": 10.0, "close": 10.1, "volume": 1},
        {"open": 10.2, "high": 11.0, "low": 9.5, "close": 9.8, "volume": 1},
    ]))
    assert gaps.iloc[0]["type"] == "bearish"


def test_overlapping_candles_produce_no_gap():
    assert smc.fair_value_gaps(frame([
        {"open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1},
        {"open": 10.5, "high": 11.5, "low": 9.5, "close": 11, "volume": 1},
        {"open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 1},
    ])).empty


def test_sweep_needs_the_close_back_inside_the_range():
    rows = [{"open": 10, "high": 10.5, "low": 9.5, "close": 10, "volume": 1}] * 20
    swept = rows + [{"open": 10, "high": 12.0, "low": 9.9, "close": 10.1, "volume": 1}]
    broke_out = rows + [{"open": 10, "high": 12.0, "low": 9.9, "close": 11.8, "volume": 1}]

    assert len(smc.liquidity_sweeps(frame(swept))) == 1
    assert smc.liquidity_sweeps(frame(swept)).iloc[0]["type"] == "buy_side"
    assert smc.liquidity_sweeps(frame(broke_out)).empty


def test_detections_have_stable_columns_even_when_empty():
    empty = frame([{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}] * 3)
    assert list(smc.fair_value_gaps(empty).columns) == smc.FVG_COLUMNS
    assert list(smc.liquidity_sweeps(empty).columns) == smc.SWEEP_COLUMNS


def test_analyse_returns_both_detections(prices):
    gaps, sweeps = smc.analyse(prices)
    assert len(gaps) > 0 and len(sweeps) > 0
