"""
Technical indicators.

Uses the `ta` package when it is installed and falls back to equivalent pandas
implementations otherwise, so the platform still runs on a bare install.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD, SMAIndicator

    TA_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised only without `ta`
    TA_AVAILABLE = False

SMA_SHORT, SMA_LONG, EMA_SHORT = 20, 50, 20
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    # min_periods matches `ta`'s EMAIndicator: without it, the pandas fallback
    # returns a numeric value seeded from bar 0 during warm-up instead of NaN,
    # which can fire spurious MACD crossovers that only exist because the EMA
    # hasn't converged yet - a discrepancy that once made the two paths
    # disagree on the same backtest (see CLAUDE.md).
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    strength = avg_gain / avg_loss.replace(0, np.nan)
    values = 100 - (100 / (1 + strength))
    # No losses in the window means maximum strength, not an undefined ratio.
    values = values.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    # No movement at all - a halted or wholly illiquid stretch - is neutral,
    # not undefined. Kept here (not only in `flat_window`) so `rsi()` is
    # correct standalone, independent of `enrich()`.
    return values.mask((avg_loss == 0) & (avg_gain == 0), 50.0)


def flat_window(close: pd.Series, period: int) -> pd.Series:
    """Where price hasn't moved at all for `period` bars running.

    `ta`'s RSIIndicator reads "no losses" as maximum strength and reports 100
    even when there were no gains either - a halted or wholly illiquid
    instrument, not genuine strength. Applied after either RSI implementation,
    this keeps both paths reading a flat market as neutral (50).
    """
    moved = (close.diff().fillna(1) != 0).astype(int)
    return moved.rolling(window=period, min_periods=period).max() == 0


def macd(series: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW,
         signal: int = MACD_SIGNAL) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(series, fast) - ema(series, slow)
    signal_line = ema(line, signal)
    return line, signal_line, line - signal_line


REQUIRED = {"sma_20", "sma_50", "ema_20", "rsi", "macd", "macd_signal", "macd_diff"}


def ensure(frame: pd.DataFrame) -> pd.DataFrame:
    """A frame that definitely has indicator columns.

    Strategies go through this so a signal never depends on who prepared the
    frame: computing RSI here and reading an enriched column elsewhere can use
    two different implementations and give two different answers.
    """
    return frame if REQUIRED <= set(frame.columns) else enrich(frame)


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with sma_20, sma_50, ema_20, rsi, macd, macd_signal and
    macd_diff attached. Column names are fixed: strategies and charts read them."""
    out = frame.copy()
    close = out["close"]

    if TA_AVAILABLE:
        out[f"sma_{SMA_SHORT}"] = SMAIndicator(close, window=SMA_SHORT).sma_indicator()
        out[f"sma_{SMA_LONG}"] = SMAIndicator(close, window=SMA_LONG).sma_indicator()
        out[f"ema_{EMA_SHORT}"] = EMAIndicator(close, window=EMA_SHORT).ema_indicator()
        out["rsi"] = RSIIndicator(close, window=RSI_PERIOD).rsi()
        indicator = MACD(close, window_fast=MACD_FAST, window_slow=MACD_SLOW,
                         window_sign=MACD_SIGNAL)
        out["macd"], out["macd_signal"] = indicator.macd(), indicator.macd_signal()
        out["macd_diff"] = indicator.macd_diff()
    else:  # pragma: no cover - exercised only without `ta`
        out[f"sma_{SMA_SHORT}"] = sma(close, SMA_SHORT)
        out[f"sma_{SMA_LONG}"] = sma(close, SMA_LONG)
        out[f"ema_{EMA_SHORT}"] = ema(close, EMA_SHORT)
        out["rsi"] = rsi(close)
        out["macd"], out["macd_signal"], out["macd_diff"] = macd(close)

    # Applied regardless of which path just ran, so a genuinely flat market
    # reads the same way whether or not `ta` is installed.
    out.loc[flat_window(close, RSI_PERIOD), "rsi"] = 50.0

    return out
