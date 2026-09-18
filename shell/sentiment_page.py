"""
Sentiment page: SentimentFinance's lexicon over live headlines or a feed file.

A thin view over the same functions analyze.py calls - score_text,
load_headlines, score_headlines - so scores match the CLI exactly.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shell import context, market
from shell.surfaces import SENTIMENT_DIR, use_sentiment

use_sentiment()
from feed import Headline, load_headlines  # noqa: E402
from sentiment import score_headlines, score_text  # noqa: E402

SAMPLE_FEED = SENTIMENT_DIR / "data" / "headlines.txt"
COLORS = {"BULLISH": "#00C853", "NEUTRAL": "#FFD600", "BEARISH": "#FF5252"}
MOMENTUM_BAND = 0.05  # same thresholds analyze.py uses for improving/deteriorating


def momentum_word(value: float) -> str:
    if value > MOMENTUM_BAND:
        return "improving"
    if value < -MOMENTUM_BAND:
        return "deteriorating"
    return "flat"


def _terms(hits) -> str:
    return ", ".join(f"{word} {weight:+.1f}" for word, weight in hits) or "no scored terms"


def live_headlines(symbol: str) -> tuple[list[Headline], list[dict]]:
    stories = market.news(symbol)
    return [Headline(date=s["published"].date(), ticker=symbol, text=s["title"])
            for s in stories], stories


def _load_feed(upload) -> tuple[list, str]:
    if upload is None:
        return load_headlines(SAMPLE_FEED), "sample feed"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "feed.txt"
        path.write_bytes(upload.getvalue())
        try:
            return load_headlines(path), upload.name
        except ValueError as exc:
            # load_headlines reports the temp path; show the user's file name.
            raise ValueError(str(exc).replace(str(path), upload.name)) from None


def _layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(template="plotly_dark", height=height, showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig


def _ticker_detail(s, headlines: list[Headline], key: str, stories: list[dict] | None = None) -> None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sentiment", s.label)
    m2.metric("Average score", f"{s.mean:+.3f}")
    m3.metric("Momentum", momentum_word(s.momentum).title(), f"{s.momentum:+.3f}")
    m4.metric("Confidence", s.confidence)

    if len(s.by_day) > 1:
        tone = go.Figure(go.Scatter(x=[str(d) for d in s.by_day], y=list(s.by_day.values()),
                                    mode="lines+markers",
                                    line=dict(color=COLORS[s.label], width=2)))
        tone.add_hline(y=0, line_color="#8892A4", line_dash="dot")
        tone.update_yaxes(range=[-1.05, 1.05], title="daily tone")
        tone.update_xaxes(type="category")
        st.plotly_chart(_layout(tone, 240), width="stretch", key=f"{key}_tone")

    rows = []
    for i, (h, sc) in enumerate(zip(headlines, s.scores)):
        row = {"Date": str(h.date), "Score": round(sc.score, 3), "Label": sc.label,
               "Headline": h.text, "Matched terms": _terms(sc.hits)}
        if stories is not None:
            row["Source"] = stories[i]["publisher"]
            row["Link"] = stories[i]["url"]
        rows.append(row)
    config = {"Link": st.column_config.LinkColumn("Link", display_text="open")} if stories else None
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config=config, key=f"{key}_table")


def _live_section(symbol: str) -> None:
    try:
        headlines, stories = live_headlines(symbol)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not fetch headlines for {symbol}: {exc}")
        return
    if not headlines:
        st.info(f"Yahoo Finance has no recent headlines for {symbol}.")
        return
    # Keep headlines and their source rows in the order score_headlines scores them.
    order = sorted(range(len(headlines)), key=lambda i: headlines[i].date)
    headlines = [headlines[i] for i in order]
    stories = [stories[i] for i in order]
    s = score_headlines(headlines)[symbol]
    st.caption(f"{len(headlines)} recent Yahoo Finance headlines for {symbol}. Yahoo's feed "
               "for a ticker can include broader market stories.")
    _ticker_detail(s, headlines, "sent_live", stories)


def _feed_section(symbol: str, upload) -> None:
    try:
        headlines, source = _load_feed(upload)
    except ValueError as exc:
        st.error(f"Could not read the feed: {exc}")
        return
    if not headlines:
        st.warning("The feed has no headlines.")
        return

    sentiments = score_headlines(headlines)
    st.caption(f"{len(headlines)} headlines across {len(sentiments)} tickers · {source}")

    rows = []
    for ticker in sorted(sentiments):
        s = sentiments[ticker]
        counts = s.counts
        rows.append({"Ticker": ticker, "Sentiment": s.label, "Score": round(s.mean, 3),
                     "Momentum": f"{s.momentum:+.3f} ({momentum_word(s.momentum)})",
                     "Confidence": s.confidence, "Bullish": counts["bullish"],
                     "Neutral": counts["neutral"], "Bearish": counts["bearish"],
                     "Headlines": len(s.scores)})
    table = pd.DataFrame(rows)

    left, right = st.columns([3, 2])
    with left:
        st.dataframe(table, hide_index=True, width="stretch", key="sent_feed_table")
    with right:
        fig = go.Figure(go.Bar(x=table["Score"], y=table["Ticker"], orientation="h",
                               marker_color=[COLORS[l] for l in table["Sentiment"]],
                               text=[f"{v:+.3f}" for v in table["Score"]], textposition="outside"))
        fig.update_xaxes(range=[-1, 1], zeroline=True, zerolinecolor="#8892A4")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(_layout(fig, 60 + 45 * len(table)), width="stretch", key="sent_feed_bars")

    st.subheader("Ticker detail")
    tickers = sorted(sentiments)
    if symbol not in tickers:
        st.caption(f"{symbol} is not in this feed; pick one of its tickers.")
    chosen = st.selectbox("Ticker", tickers, key="sentiment_ticker",
                          index=tickers.index(symbol) if symbol in tickers else 0)
    _ticker_detail(sentiments[chosen], [h for h in headlines if h.ticker == chosen], "sent_feed")


def render() -> None:
    symbol = context.ticker()
    st.title("News Sentiment")
    st.caption("Finance-tuned lexicon scoring of headlines, from -1 (bearish) to +1 (bullish). "
               "It measures how the news reads, not where the price is going.")

    st.subheader("Score a headline")
    text = st.text_input("Headline", value="Nvidia beats estimates but warns of weak demand",
                         key="sentiment_text")
    if text.strip():
        score = score_text(text)
        c1, c2, c3 = st.columns([1, 1, 3])
        c1.metric("Score", f"{score.score:+.3f}")
        c2.metric("Label", score.label.title())
        # Not a metric: metric values truncate, and headlines often match 4+ terms.
        c3.caption("Matched terms")
        c3.markdown(" ".join(f"`{w} {v:+.1f}`" for w, v in score.hits) or "_no scored terms_")

    st.divider()
    source = st.segmented_control(
        "Headlines", [f"Live news · {symbol}", "Sample feed", "Upload feed"],
        default=f"Live news · {symbol}", key=f"sentiment_source_{symbol}")
    if source is None or source.startswith("Live"):
        st.subheader(f"{symbol} in the news")
        _live_section(symbol)
    else:
        upload = None
        if source == "Upload feed":
            upload = st.file_uploader(
                "Feed file: one `YYYY-MM-DD | TICKER | headline` per line",
                type=["txt"], key="sentiment_upload")
            if upload is None:
                st.info("Upload a feed file to score it.")
                return
        st.subheader("Feed")
        _feed_section(symbol, upload)
