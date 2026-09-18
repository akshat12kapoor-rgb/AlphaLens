"""
Offline fixtures.

`install()` points the data layer at committed snapshots, so the app, the
driver and the tests can run with no network and identical numbers. Nothing in
the product calls it; it is opt-in from tests and the offline server.
"""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from alphalens.core.config import FIXTURES
from alphalens.data import yahoo
from alphalens.data.models import Fundamentals, Quote, Story

PRICES = FIXTURES / "AAPL_prices.csv"
FUNDAMENTALS = FIXTURES / "AAPL_fundamentals.json"
NEWS = FIXTURES / "AAPL_news.json"


def price_frame() -> pd.DataFrame:
    frame = pd.read_csv(PRICES, index_col=0, parse_dates=True)
    frame.index.name = None
    return frame


def fundamentals(symbol: str = "AAPL") -> Fundamentals:
    raw = json.loads(FUNDAMENTALS.read_text())
    series = {k: pd.Series(v["__series__"], dtype="float64")
              for k, v in raw.items() if isinstance(v, dict) and "__series__" in v}
    return Fundamentals(
        symbol=symbol.upper(), name=raw["company_name"], currency="USD",
        price=raw["current_price"], shares_outstanding=raw["shares_outstanding"],
        revenue=raw["revenue"], free_cash_flow=raw["fcf"], ebitda=raw["ebitda"],
        net_income=raw["net_income"], eps=raw["eps"], total_debt=raw["total_debt"],
        cash=raw["cash"], sector=raw["sector"], industry=raw["industry"],
        revenue_history=series.get("revenue_history", pd.Series(dtype="float64")),
        fcf_history=series.get("fcf_history", pd.Series(dtype="float64")),
    )


def stories() -> list[Story]:
    raw = json.loads(NEWS.read_text())["stories"]
    return sorted((Story(title=s["title"], published=datetime.fromisoformat(s["published"]),
                         publisher=s["publisher"], url=s["url"]) for s in raw),
                  key=lambda s: s.published)


def install() -> None:
    """Serve every symbol from the AAPL snapshots, relabelled to the symbol asked
    for. Numbers stay AAPL's - that is the point of a fixture, not a simulation
    of other companies."""
    frame = price_frame()
    snapshot = fundamentals()
    feed = stories()

    yahoo.prices = lambda symbol, period="2y", interval="1d": frame.copy()
    yahoo.fundamentals = lambda symbol: Fundamentals(
        **{**snapshot.__dict__, "symbol": symbol.upper()})
    yahoo.fetch_news = lambda symbol: list(feed)
    yahoo.news = lambda symbol: list(feed)
    yahoo.quote = lambda symbol: Quote(
        symbol=symbol.upper(), name=snapshot.name, currency=snapshot.currency,
        sector=snapshot.sector, industry=snapshot.industry, price=snapshot.price)
