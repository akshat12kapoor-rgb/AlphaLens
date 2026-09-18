"""
The active ticker, and safe access to its data.

One symbol flows through every page, so moving between tools never loses the
instrument you are looking at. The sidebar picker in app.py is the only place it
is set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import streamlit as st

from alphalens.core.config import DEFAULT_TICKER
from alphalens.data import yahoo
from alphalens.data.models import Fundamentals, Quote

TICKER_KEY = "alphaos_ticker"
PICKER_KEY = "alphaos_ticker_picker"
#: Set by the backtester to hand a strategy to the simulator.
SIM_REQUEST_KEY = "alphaos_sim_request"

POPULAR = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "AMD", "NFLX",
    "JPM", "BAC", "GS", "V", "MA", "BRK-B",
    "UNH", "JNJ", "LLY", "XOM", "CVX", "WMT", "KO", "BA", "CAT",
    "SPY", "QQQ", "DIA", "GLD",
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "BTC-USD", "ETH-USD",
]


def normalise(symbol: str) -> str:
    return symbol.strip().upper().replace(" ", "")


def ticker() -> str:
    return st.session_state.get(TICKER_KEY, DEFAULT_TICKER)


def set_ticker(symbol: str) -> None:
    symbol = normalise(symbol)
    if symbol:
        st.session_state[TICKER_KEY] = symbol


def render_picker() -> str:
    """The sidebar ticker picker. Accepts any Yahoo symbol, not just suggestions."""
    if TICKER_KEY not in st.session_state:
        st.session_state[TICKER_KEY] = DEFAULT_TICKER
    current = ticker()
    options = POPULAR if current in POPULAR else [current, *POPULAR]
    # Keep the widget in step when the ticker was set elsewhere (e.g. a handoff).
    if st.session_state.get(PICKER_KEY) != current:
        st.session_state[PICKER_KEY] = current
    st.selectbox("Active ticker", options, key=PICKER_KEY,
                 on_change=lambda: set_ticker(st.session_state.get(PICKER_KEY) or ""),
                 accept_new_options=True,
                 help="Every AlphaOS tool works on this ticker. Type any Yahoo Finance "
                      "symbol, for example SHOP, RELIANCE.NS or BTC-USD.")
    return ticker()


# ── data access that degrades instead of breaking the page ──────────────────

@dataclass
class Attempt:
    """The outcome of a data call: either a value or a message to show."""

    ok: bool
    value: Any = None
    error: str = ""


def attempt(call: Callable, *args, **kwargs) -> Attempt:
    """Run a data call so one failure (bad symbol, rate limit, missing statement)
    degrades a single card rather than the whole page."""
    try:
        return Attempt(True, call(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - shown to the user verbatim
        return Attempt(False, error=str(exc).strip().splitlines()[0][:220])


def quote(symbol: str) -> Quote:
    return yahoo.quote(symbol)


def prices(symbol: str, period: str = "2y", interval: str = "1d"):
    return yahoo.prices(symbol, period=period, interval=interval)


def fundamentals(symbol: str) -> Fundamentals:
    return yahoo.fundamentals(symbol)


def news(symbol: str):
    return yahoo.news(symbol)


def currency_of(symbol: str) -> str:
    """The instrument's currency, falling back to a suffix guess if Yahoo is
    unreachable - never silently showing another currency's symbol."""
    from alphalens.core.currency import guess_currency

    found = attempt(quote, symbol)
    return found.value.currency if found.ok else guess_currency(symbol)
