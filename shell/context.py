"""
The active ticker: AlphaOS's one piece of shared context.

Every tool reads it, and the sidebar picker in app.py is the only place it is
set, so moving between tools never loses the instrument you are looking at.
"""
from __future__ import annotations

import streamlit as st

TICKER_KEY = "alphaos_ticker"
DEFAULT_TICKER = "AAPL"
_WIDGET_KEY = "alphaos_ticker_picker"

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


def _on_pick() -> None:
    set_ticker(st.session_state.get(_WIDGET_KEY) or "")


def render_picker() -> str:
    """Sidebar picker. Accepts any Yahoo symbol, not just the suggestions."""
    # Store the default on first render so the key always exists for readers.
    if TICKER_KEY not in st.session_state:
        st.session_state[TICKER_KEY] = DEFAULT_TICKER
    current = ticker()
    options = POPULAR if current in POPULAR else [current, *POPULAR]
    # Keep the widget in step when the ticker was set elsewhere (e.g. a handoff).
    if st.session_state.get(_WIDGET_KEY) != current:
        st.session_state[_WIDGET_KEY] = current
    st.selectbox(
        "Active ticker",
        options,
        key=_WIDGET_KEY,
        on_change=_on_pick,
        accept_new_options=True,
        help="Every AlphaOS tool works on this ticker. Type any Yahoo Finance "
             "symbol, e.g. SHOP, RELIANCE.NS, BTC-USD.",
    )
    return ticker()
