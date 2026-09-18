"""
Smart Money Concepts: Fair Value Gaps and liquidity sweeps.

Both are detected from bars that have already closed, so a strategy built on
them can be backtested without look-ahead:

- An FVG is a three-candle imbalance recorded at its middle bar; it is only
  knowable once the third candle closes, which is why strategies act at
  `start_idx + 1`.
- A sweep compares bar i against the 20 bars before it.
"""
from __future__ import annotations

import pandas as pd

SWEEP_LOOKBACK = 20

FVG_COLUMNS = ["index", "type", "top", "bottom", "mid", "start_idx"]
SWEEP_COLUMNS = ["index", "type", "wick_price", "close_price", "swept_level"]

FVG_EXPLANATION = (
    "A **Fair Value Gap** is a three-candle imbalance: price moves so fast that "
    "candle 1 and candle 3 do not overlap. The gap often acts as support "
    "(bullish) or resistance (bearish) when price returns to it."
)
SWEEP_EXPLANATION = (
    "A **liquidity sweep** is a wick beyond a prior swing high or low that closes "
    "back inside the range - a stop hunt. It often marks a reversal, because the "
    "orders resting beyond the level have been filled."
)


def fair_value_gaps(frame: pd.DataFrame) -> pd.DataFrame:
    """Three-candle imbalances.

    Bullish: candle[i+1].low > candle[i-1].high. Bearish: the mirror image.
    """
    highs, lows, times = frame["high"].values, frame["low"].values, frame.index
    records = []
    for i in range(1, len(frame) - 1):
        if lows[i + 1] > highs[i - 1]:
            top, bottom, kind = lows[i + 1], highs[i - 1], "bullish"
        elif highs[i + 1] < lows[i - 1]:
            top, bottom, kind = lows[i - 1], highs[i + 1], "bearish"
        else:
            continue
        records.append({"index": times[i], "type": kind, "top": top, "bottom": bottom,
                        "mid": (top + bottom) / 2, "start_idx": i})
    return pd.DataFrame(records, columns=FVG_COLUMNS)


def liquidity_sweeps(frame: pd.DataFrame, lookback: int = SWEEP_LOOKBACK) -> pd.DataFrame:
    """Wicks beyond the prior `lookback` bars' extreme that close back inside."""
    highs, lows, closes = frame["high"].values, frame["low"].values, frame["close"].values
    times = frame.index
    records = []
    for i in range(lookback, len(frame)):
        prior_high = highs[i - lookback:i].max()
        prior_low = lows[i - lookback:i].min()
        if highs[i] > prior_high and closes[i] < prior_high:
            kind, wick, level = "buy_side", highs[i], prior_high
        elif lows[i] < prior_low and closes[i] > prior_low:
            kind, wick, level = "sell_side", lows[i], prior_low
        else:
            continue
        records.append({"index": times[i], "type": kind, "wick_price": wick,
                        "close_price": closes[i], "swept_level": level})
    return pd.DataFrame(records, columns=SWEEP_COLUMNS)


def analyse(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Both detectors in one call: (fair value gaps, liquidity sweeps)."""
    return fair_value_gaps(frame), liquidity_sweeps(frame)
