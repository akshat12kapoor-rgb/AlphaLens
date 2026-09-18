"""Typed results from the data layer.

The old tools passed dicts around and each rediscovered which keys might be
missing. These dataclasses make the optional fields explicit: a company with no
earnings has `eps=None`, and every consumer has to say what it does about that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True)
class Quote:
    """Identity and last price for a symbol."""

    symbol: str
    name: str
    currency: str
    sector: str | None = None
    industry: str | None = None
    price: float | None = None
    exchange: str | None = None
    market_cap: float | None = None


@dataclass(frozen=True)
class Fundamentals:
    """Everything the valuation models need, normalised from Yahoo.

    Any field except `symbol`, `name` and `currency` can be missing: Yahoo's
    statements are patchy, and instruments like crypto and ETFs have none.
    """

    symbol: str
    name: str
    currency: str
    price: float | None = None
    shares_outstanding: float | None = None
    revenue: float | None = None
    free_cash_flow: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    eps: float | None = None
    total_debt: float = 0.0
    cash: float = 0.0
    sector: str | None = None
    industry: str | None = None
    revenue_history: pd.Series = field(default_factory=lambda: pd.Series(dtype="float64"))
    fcf_history: pd.Series = field(default_factory=lambda: pd.Series(dtype="float64"))

    def require(self, *fields: str) -> None:
        """Raise a readable error naming what this symbol is missing."""
        missing = [f for f in fields if not getattr(self, f)]
        if missing:
            raise MissingData(
                f"{self.symbol} has no " + ", ".join(m.replace('_', ' ') for m in missing)
                + ". Yahoo Finance publishes no such data for this instrument."
            )


@dataclass(frozen=True)
class Story:
    """One news item."""

    title: str
    published: datetime
    publisher: str = ""
    url: str = ""

    @property
    def day(self) -> date:
        return self.published.date()


class MissingData(Exception):
    """Raised when a symbol lacks the data a tool needs."""


class DataUnavailable(Exception):
    """Raised when the feed could not be reached or returned nothing."""
