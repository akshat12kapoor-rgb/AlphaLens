"""The watchlist's session-state bookkeeping and scoring: no Streamlit
runtime needed, `st.session_state` behaves as a plain dict outside
`streamlit run`."""
import streamlit as st

from alphalens.ui.pages.overview import Read
from alphalens.ui.pages.watchlist import MAX_TICKERS, WATCHLIST_KEY, _add, _remove, bullish_count


def teardown_function():
    st.session_state.pop(WATCHLIST_KEY, None)


def test_add_accepts_a_plausible_ticker():
    st.session_state[WATCHLIST_KEY] = ["AAPL"]
    _add("msft")
    assert st.session_state[WATCHLIST_KEY] == ["AAPL", "MSFT"]


def test_add_ignores_garbage_input():
    st.session_state[WATCHLIST_KEY] = ["AAPL"]
    _add("'; DROP TABLE tickers;--")
    assert st.session_state[WATCHLIST_KEY] == ["AAPL"]


def test_add_ignores_a_duplicate():
    st.session_state[WATCHLIST_KEY] = ["AAPL"]
    _add("AAPL")
    assert st.session_state[WATCHLIST_KEY] == ["AAPL"]


def test_add_is_capped_at_max_tickers():
    st.session_state[WATCHLIST_KEY] = [f"T{i}" for i in range(MAX_TICKERS)]
    _add("ONEMORE")
    assert len(st.session_state[WATCHLIST_KEY]) == MAX_TICKERS


def test_remove_drops_the_ticker():
    st.session_state[WATCHLIST_KEY] = ["AAPL", "MSFT"]
    _remove("AAPL")
    assert st.session_state[WATCHLIST_KEY] == ["MSFT"]


def test_remove_of_a_missing_ticker_is_a_no_op():
    st.session_state[WATCHLIST_KEY] = ["AAPL"]
    _remove("MSFT")
    assert st.session_state[WATCHLIST_KEY] == ["AAPL"]


def test_bullish_count_ignores_bearish_neutral_context_and_none():
    reads = [Read("Valuation", "bullish", "says BUY"),
             Read("Sentiment", "bullish", "reads bullish"),
             Read("Backtest", "context", "beating buy & hold"),
             Read("Technicals", "bearish", "is in a downtrend"),
             None]
    assert bullish_count(reads) == 2


def test_bullish_count_of_no_reads_is_zero():
    assert bullish_count([None, None]) == 0
