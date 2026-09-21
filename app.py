"""
AlphaLens - the financial analysis and trading simulation platform.

    .venv/bin/streamlit run app.py

One Streamlit app over four tools that share an active ticker:

    Overview             what every tool says about the ticker right now
    Watchlist            several tickers at once, same four lenses, compared
    Valuation            DCF and comparable multiples
    News Sentiment       lexicon scoring of headlines
    Strategy Backtester   strategies against history, with parameter sweeps
    Trading Simulator    candle-by-candle replay and paper trading

Each page is a thin script in views/ so Streamlit (and AppTest) can address it
by path; the page code lives in alphalens.ui.pages.
"""
import streamlit as st

from alphalens.ui import context

st.set_page_config(page_title="AlphaLens", page_icon="🧭", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = {
    "AlphaLens": [
        st.Page("views/overview.py", title="Overview", icon=":material/dashboard:",
                url_path="overview", default=True),
        st.Page("views/watchlist.py", title="Watchlist", icon=":material/list_alt:",
                url_path="watchlist"),
    ],
    "Research": [
        st.Page("views/valuation.py", title="Valuation", icon=":material/calculate:",
                url_path="valuation"),
        st.Page("views/sentiment.py", title="News Sentiment", icon=":material/newspaper:",
                url_path="sentiment"),
    ],
    "Strategy": [
        st.Page("views/backtester.py", title="Strategy Backtester",
                icon=":material/query_stats:", url_path="backtester"),
        st.Page("views/simulator.py", title="Trading Simulator",
                icon=":material/candlestick_chart:", url_path="simulator"),
    ],
}

navigation = st.navigation(PAGES)

with st.sidebar:
    context.render_picker()
    st.divider()

navigation.run()
