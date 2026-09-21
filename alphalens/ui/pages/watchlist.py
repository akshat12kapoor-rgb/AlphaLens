"""Watchlist: several tickers at once, each read through the same four
lenses as the Overview page, plus a head-to-head comparison of any two.

Session-only by design (like everything else in AlphaLens's session state):
there's no account system to persist it against, so it resets when the
browser session ends. Naming it "Watchlist" rather than "Portfolio" is
deliberate - nothing here tracks holdings or cost basis, only what the four
tools currently say about each symbol.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from alphalens.core.currency import money
from alphalens.ui import context, layout
from alphalens.ui.pages.overview import gather_reads, join_names, takeaway

WATCHLIST_KEY = "alphalens_watchlist"
#: Each ticker costs 4 Yahoo round trips (price, fundamentals, news, and the
#: backtest reuses price). A long list turns one page load into dozens of
#: sequential fetches, so it's capped rather than left to grow unbounded.
MAX_TICKERS = 10


def _watchlist() -> list[str]:
    if WATCHLIST_KEY not in st.session_state:
        st.session_state[WATCHLIST_KEY] = [context.ticker()]
    return st.session_state[WATCHLIST_KEY]


def _add(symbol: str) -> None:
    symbol = context.normalise(symbol)
    if not symbol or not context.TICKER_RE.match(symbol):
        return
    watchlist = _watchlist()
    if symbol not in watchlist and len(watchlist) < MAX_TICKERS:
        watchlist.append(symbol)


def _remove(symbol: str) -> None:
    watchlist = _watchlist()
    if symbol in watchlist:
        watchlist.remove(symbol)


def _row(symbol: str) -> dict:
    """One watchlist ticker's snapshot: last close plus its four reads,
    reusing exactly what the Overview page computes for the active ticker."""
    history = context.attempt(context.prices, symbol, "6mo", "1d")
    currency = context.currency_of(symbol)
    close = money(float(history.value["close"].iloc[-1]), currency) if history.ok else "—"
    reads = gather_reads(symbol)
    labels = {r.name: r.detail for r in reads if r is not None}
    return {"Ticker": symbol, "Last close": close,
            "Valuation": labels.get("Valuation", "—"),
            "Sentiment": labels.get("Sentiment", "—"),
            "Takeaway": takeaway(reads) or "Not enough data yet.",
            "_reads": reads}


def _table(rows: list[dict]) -> None:
    frame = pd.DataFrame([{k: v for k, v in row.items() if k != "_reads"} for row in rows])
    st.dataframe(frame, hide_index=True, width="stretch", key="watchlist_table")


def bullish_count(reads: list) -> int:
    return sum(1 for r in reads if r is not None and r.lean == "bullish")


def _compare(rows: list[dict]) -> None:
    if len(rows) < 2:
        st.caption("Add a second ticker to compare them head to head.")
        return
    tickers = [row["Ticker"] for row in rows]
    left, right = st.columns(2)
    a = left.selectbox("Ticker A", tickers, index=0, key="watchlist_compare_a")
    remaining = [t for t in tickers if t != a] or tickers
    b = right.selectbox("Ticker B", remaining, index=0, key="watchlist_compare_b")
    if a == b:
        st.caption("Pick two different tickers.")
        return

    row_a = next(r for r in rows if r["Ticker"] == a)
    row_b = next(r for r in rows if r["Ticker"] == b)
    by_name_a = {r.name: r for r in row_a["_reads"] if r is not None}
    by_name_b = {r.name: r for r in row_b["_reads"] if r is not None}

    table = [{"Lens": name, a: (by_name_a[name].detail if name in by_name_a else "—"),
             b: (by_name_b[name].detail if name in by_name_b else "—")}
             for name in ("Valuation", "Sentiment", "Backtest", "Technicals")]
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch", key="watchlist_compare")

    score_a, score_b = bullish_count(row_a["_reads"]), bullish_count(row_b["_reads"])
    if score_a == score_b:
        st.caption(f"{a} and {b} read equally bullish across the lenses that take a side "
                   "(valuation, sentiment, technicals) - the backtest column above is "
                   "shown for context but isn't counted here either, same as the "
                   "Overview takeaway.")
    else:
        leader, count, other, other_count = (
            (a, score_a, b, score_b) if score_a > score_b else (b, score_b, a, score_a))
        st.caption(f"{leader} reads bullish on more lenses ({count} vs {other_count} for "
                   f"{other}) - a count, not a recommendation.")


def render() -> None:
    layout.page_header("Watchlist",
                       "Several tickers at once, each read through Valuation, Sentiment, "
                       "the Backtest and Technicals - the same four lenses as Overview.")

    watchlist = _watchlist()

    add_col, button_col = st.columns([4, 1])
    new_symbol = add_col.text_input("Add a ticker", key="watchlist_add",
                                    placeholder="e.g. MSFT, RELIANCE.NS, BTC-USD",
                                    label_visibility="collapsed")
    if button_col.button("Add", width="stretch", key="watchlist_add_btn",
                         disabled=len(watchlist) >= MAX_TICKERS):
        _add(new_symbol)
        st.rerun()
    if len(watchlist) >= MAX_TICKERS:
        st.caption(f"Up to {MAX_TICKERS} tickers - each one costs a full round of "
                   "fetches, same as loading Overview once per symbol.")

    if not watchlist:
        st.info("Add a ticker above to start a watchlist.")
        return

    with st.spinner(f"Reading {len(watchlist)} ticker(s)…"):
        rows = [_row(symbol) for symbol in watchlist]

    _table(rows)

    remove_col, _ = st.columns([2, 3])
    with remove_col:
        to_remove = st.selectbox("Remove a ticker", watchlist, key="watchlist_remove_pick",
                                 label_visibility="collapsed")
        if st.button(f"Remove {to_remove}", key="watchlist_remove_btn"):
            _remove(to_remove)
            st.rerun()

    st.divider()
    st.subheader("Compare two tickers")
    _compare(rows)

    st.caption("Session-only: this list is not saved anywhere and resets when the "
               "browser session ends.")
