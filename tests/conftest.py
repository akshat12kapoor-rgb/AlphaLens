"""Shared fixtures. Nothing here touches the network."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alphalens.data import csv_prices, fixtures
from alphalens.signals import indicators
from alphalens.signals.strategies import Context


@pytest.fixture(scope="session")
def prices() -> pd.DataFrame:
    """500 real daily AAPL bars."""
    return fixtures.price_frame()


@pytest.fixture(scope="session")
def enriched(prices) -> pd.DataFrame:
    return indicators.enrich(prices)


@pytest.fixture(scope="session")
def context(enriched) -> Context:
    return Context.for_frame(enriched)


@pytest.fixture(scope="session")
def sample() -> pd.DataFrame:
    """400 synthetic bars shipped with the platform."""
    frame, _ = csv_prices.sample_prices()
    return frame


@pytest.fixture(scope="session")
def fundamentals():
    return fixtures.fundamentals()


@pytest.fixture
def synthetic() -> pd.DataFrame:
    """A deterministic random walk, for tests that need arbitrary shapes."""
    rng = np.random.default_rng(7)
    n = 200
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    return pd.DataFrame(
        {"open": close + rng.normal(0, 0.4, n),
         "high": close * (1 + abs(rng.normal(0, 0.01, n))),
         "low": close * (1 - abs(rng.normal(0, 0.01, n))),
         "close": close,
         "volume": rng.integers(1e5, 1e6, n)},
        index=pd.date_range("2024-01-01", periods=n, freq="D"))
