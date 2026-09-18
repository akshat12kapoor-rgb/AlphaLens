"""
Shared, cached data access for AlphaOS pages.

Price history and fundamentals go through the surfaces' own fetchers, so the
platform, the simulator and the valuation page all read identical numbers (and
test fixtures patched into those fetchers apply everywhere).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import streamlit as st

from shell import surfaces

TTL = 15 * 60

# The valuation page's default assumptions (stock-valuation-dashboard/app.py
# sidebar). The overview's verdict must match what that page shows on load.
DEFAULT_VALUATION = dict(growth_rate=0.10, stage1_years=5, stage2_years=0,
                         wacc=0.10, terminal_growth=0.03, dcf_weight=0.60)


@st.cache_data(ttl=TTL, show_spinner=False)
def price_history(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Lowercase OHLCV, cleaned by the simulator's fetcher."""
    return surfaces.module(surfaces.SIMULATOR, "data_fetcher").fetch_data(
        symbol, period=period, interval=interval)


@st.cache_data(ttl=TTL, show_spinner=False)
def fundamentals(symbol: str) -> dict:
    return surfaces.module(surfaces.VALUATION, "data_fetcher").fetch_stock_data(symbol)


def fetch_news(symbol: str) -> list[dict]:
    """Recent Yahoo Finance stories for a symbol, as
    {title, publisher, published (datetime), url}. Yahoo's feed for a ticker
    can include broader market stories, not only company news."""
    import yfinance as yf

    stories = []
    for item in yf.Ticker(symbol).news or []:
        content = item.get("content") or item
        title = (content.get("title") or "").strip()
        if not title:
            continue
        stamp = content.get("pubDate") or content.get("displayTime")
        try:
            published = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        url = ((content.get("canonicalUrl") or {}).get("url")
               or (content.get("clickThroughUrl") or {}).get("url") or "")
        stories.append({
            "title": title,
            "publisher": (content.get("provider") or {}).get("displayName", ""),
            "published": published,
            "url": url,
        })
    return stories


@st.cache_data(ttl=TTL, show_spinner=False)
def news(symbol: str) -> list[dict]:
    # Looked up at call time so tests can patch fetch_news.
    return globals()["fetch_news"](symbol)


@dataclass
class Snapshot:
    ok: bool
    value: object = None
    error: str = ""


def attempt(fn, *args, **kwargs) -> Snapshot:
    """Run a data call for an overview card without letting one failure
    (bad symbol, rate limit, missing statement) take down the whole page."""
    try:
        return Snapshot(True, fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
        return Snapshot(False, error=str(exc).strip().splitlines()[0][:200])


def default_valuation(data: dict):
    """DCF + multiples + verdict with the valuation page's default assumptions."""
    dcf = surfaces.module(surfaces.VALUATION, "dcf_model")
    multiples = surfaces.module(surfaces.VALUATION, "multiples_model")
    decision = surfaces.module(surfaces.VALUATION, "decision_engine")
    a = DEFAULT_VALUATION
    dcf_result = dcf.run_dcf(
        base_fcf=data["fcf"], shares_outstanding=data["shares_outstanding"],
        growth_rate=a["growth_rate"], wacc=a["wacc"], terminal_growth=a["terminal_growth"],
        stage1_years=a["stage1_years"], stage2_years=a["stage2_years"])
    mult_result = multiples.run_multiples_valuation(
        eps=data["eps"], ebitda=data["ebitda"], total_debt=data["total_debt"],
        cash=data["cash"], shares_outstanding=data["shares_outstanding"],
        sector=data["sector"])
    return decision.make_decision(
        ticker=data["ticker"], current_price=data["current_price"],
        dcf_value=dcf_result["intrinsic_value"],
        multiples_value=mult_result["blended_price"], dcf_weight=a["dcf_weight"])


def md(text: str) -> str:
    """Escape `$` for Streamlit markdown (captions, metric deltas), where a pair
    of dollar signs starts a LaTeX span and swallows the text between them."""
    return text.replace("$", "\\$")


def currency_symbol(symbol: str) -> str:
    """Display currency guess from the exchange suffix. Yahoo quotes .NS/.BO in INR."""
    return "₹" if symbol.upper().endswith((".NS", ".BO")) else "$"
