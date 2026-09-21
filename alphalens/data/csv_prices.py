"""Read OHLCV price data from a CSV into the platform's frame shape."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from alphalens.core.config import SAMPLES
from alphalens.data.models import DataUnavailable
from alphalens.data.yahoo import OHLCV

REQUIRED = ["Date", "Open", "High", "Low", "Close", "Volume"]
SAMPLE_PRICES = SAMPLES / "sample_prices.csv"


def load_prices(source, symbol: str | None = None) -> tuple[pd.DataFrame, str]:
    """Parse `Date,Open,High,Low,Close,Volume` into (frame, symbol).

    Rows may be in any order; the frame comes back sorted by date. Duplicate
    dates are rejected rather than silently averaged.
    """
    name = symbol or (Path(source).stem.upper() if isinstance(source, (str, Path)) else "UPLOAD")
    try:
        frame = pd.read_csv(source)
    except Exception as exc:  # noqa: BLE001
        raise DataUnavailable(f"Could not read {name}: {exc}") from exc

    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise DataUnavailable(f"{name} is missing column(s): {', '.join(missing)}")

    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    if frame["Date"].isna().any():
        bad = int(frame["Date"].isna().idxmax()) + 2  # +2: header row and 0-based index
        raise DataUnavailable(f"{name}: bad date on row {bad}; expected YYYY-MM-DD")

    frame = frame.set_index("Date").sort_index()
    if frame.index.duplicated().any():
        day = frame.index[frame.index.duplicated()][0].date()
        raise DataUnavailable(f"{name}: duplicate date {day}")

    frame = frame[["Open", "High", "Low", "Close", "Volume"]].astype("float64")
    frame.columns = OHLCV
    if frame.empty:
        raise DataUnavailable(f"{name} has no data rows")
    # Matches yahoo.prices(): a zero-volume bar (a halt, a missing trading day
    # padded with the prior close) would otherwise splice its neighbours
    # together for SMC's candle-adjacency checks, giving a different FVG/sweep
    # count for the same underlying history depending only on the data source.
    frame = frame[frame["volume"] > 0]
    if frame.empty:
        raise DataUnavailable(f"{name} has no bars with nonzero volume")
    return frame, name


def sample_prices() -> tuple[pd.DataFrame, str]:
    """400 bars of synthetic daily data, for trying a strategy with no network."""
    return load_prices(SAMPLE_PRICES, symbol="SAMPLE")
