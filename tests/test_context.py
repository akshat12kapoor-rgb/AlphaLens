"""The active ticker: normalising input and rejecting anything that isn't
ticker-shaped before it can reach a network call or a widget key."""
import streamlit as st

from alphalens.core.config import DEFAULT_TICKER
from alphalens.ui import context


def teardown_function():
    st.session_state.pop(context.TICKER_KEY, None)


def test_normalise_trims_and_uppercases():
    assert context.normalise("  aapl  ") == "AAPL"
    assert context.normalise("brk b") == "BRKB"


def test_set_ticker_accepts_a_plausible_symbol():
    context.set_ticker("reliance.ns")
    assert context.ticker() == "RELIANCE.NS"


def test_set_ticker_ignores_input_that_is_not_ticker_shaped():
    context.set_ticker("AAPL")
    context.set_ticker("'; DROP TABLE tickers;--")
    assert context.ticker() == "AAPL"


def test_set_ticker_ignores_empty_input():
    context.set_ticker("AAPL")
    context.set_ticker("   ")
    assert context.ticker() == "AAPL"


def test_ticker_defaults_when_nothing_has_been_set():
    assert context.ticker() == DEFAULT_TICKER
