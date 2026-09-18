"""
AlphaOS - financial analysis and trading simulation platform.

    .venv/bin/streamlit run app.py

One Streamlit app over four tools that share an active ticker:

    Overview            shell/home.py            the ticker through every tool at once
    Valuation           stock-valuation-dashboard/app.py (embedded)
    News Sentiment      shell/sentiment_page.py  over SentimentFinance
    Strategy Backtester shell/backtest_page.py   over AlgoBacktester + simulator strategies
    Trading Simulator   stock_simulator/app.py   (embedded)

The two embedded apps check ALPHAOS_EMBEDDED to defer to the platform; see
shell/surfaces.py for how their clashing `modules` packages coexist.
"""
import streamlit as st

from shell import context

st.set_page_config(
    page_title="AlphaOS",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = {
    "AlphaOS": [
        st.Page("views/overview.py", title="Overview", icon=":material/dashboard:",
                url_path="overview", default=True),
    ],
    "Research": [
        st.Page("views/valuation.py", title="Valuation",
                icon=":material/calculate:", url_path="valuation"),
        st.Page("views/sentiment.py", title="News Sentiment",
                icon=":material/newspaper:", url_path="sentiment"),
    ],
    "Strategy": [
        st.Page("views/backtester.py", title="Strategy Backtester",
                icon=":material/query_stats:", url_path="backtester"),
        st.Page("views/simulator.py", title="Trading Simulator",
                icon=":material/candlestick_chart:", url_path="simulator"),
    ],
}

navigation = st.navigation(pages)

with st.sidebar:
    context.render_picker()
    st.divider()

# The simulator's stylesheet hides every <header> element, which also takes out
# the navigation's section labels while that page is open. Keep them visible.
st.html("""<style>
[data-testid="stNavSectionHeader"] { visibility: visible !important; }
</style>""")

navigation.run()
