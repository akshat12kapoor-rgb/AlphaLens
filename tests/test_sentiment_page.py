"""Session-state bookkeeping on the sentiment page. No Streamlit runtime
needed: `st.session_state` behaves as a plain dict outside `streamlit run`."""
import streamlit as st

from alphalens.ui.pages import sentiment


def teardown_function():
    for key in [k for k in st.session_state if k.startswith("sentiment_source_")]:
        del st.session_state[key]


def test_switching_tickers_forgets_the_previous_tickers_source_choice():
    st.session_state["sentiment_source_AAPL"] = "Upload feed"
    sentiment._forget_other_tickers_source_choice("MSFT")
    assert "sentiment_source_AAPL" not in st.session_state


def test_the_current_tickers_own_choice_survives():
    st.session_state["sentiment_source_AAPL"] = "Upload feed"
    sentiment._forget_other_tickers_source_choice("AAPL")
    assert st.session_state["sentiment_source_AAPL"] == "Upload feed"


def test_only_one_tickers_key_is_ever_kept():
    for symbol in ["AAPL", "MSFT", "TSLA", "NVDA"]:
        sentiment._forget_other_tickers_source_choice(symbol)
        st.session_state[f"sentiment_source_{symbol}"] = "Sample feed"
    remaining = [k for k in st.session_state if k.startswith("sentiment_source_")]
    assert remaining == ["sentiment_source_NVDA"]
