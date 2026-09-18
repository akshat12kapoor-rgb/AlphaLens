"""News Sentiment: how the headlines around a ticker read."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from alphalens.charts import sentiment as sentiment_charts
from alphalens.sentiment import feed as feed_module
from alphalens.sentiment.scoring import TickerSentiment, score_headlines, score_text
from alphalens.ui import context, layout


def _headline_scorer() -> None:
    st.subheader("Score a headline")
    text = st.text_input("Headline", value="Nvidia beats estimates but warns of weak demand",
                         key="sentiment_text")
    if not text.strip():
        return
    score = score_text(text)
    columns = st.columns([1, 1, 3])
    layout.metric(columns[0], "Score", f"{score.score:+.3f}")
    layout.metric(columns[1], "Label", score.label.title())
    # Not a metric: metric values truncate, and headlines often match several terms.
    columns[2].caption("Matched terms")
    columns[2].markdown(" ".join(f"`{word} {weight:+.1f}`" for word, weight in score.hits)
                        or "_no scored terms_")


def _detail(sentiment: TickerSentiment, headlines: list, key: str,
            sources: list | None = None) -> None:
    columns = st.columns(4)
    layout.metric(columns[0], "Sentiment", sentiment.label)
    layout.metric(columns[1], "Average score", f"{sentiment.mean:+.3f}")
    layout.metric(columns[2], "Momentum", sentiment.momentum_word.title(),
                  f"{sentiment.momentum:+.3f}")
    layout.metric(columns[3], "Confidence", sentiment.confidence)

    if len(sentiment.by_day) > 1:
        st.plotly_chart(
            sentiment_charts.daily_tone([str(day) for day in sentiment.by_day],
                                        list(sentiment.by_day.values()), sentiment.label),
            width="stretch", key=f"{key}_tone")

    rows = []
    for position, (headline, score) in enumerate(zip(headlines, sentiment.scores)):
        row = {"Date": str(headline.date), "Score": round(score.score, 3),
               "Label": score.label, "Headline": headline.text, "Matched terms": score.terms}
        if sources:
            row["Source"] = sources[position].publisher
            row["Link"] = sources[position].url
        rows.append(row)
    configuration = {"Link": st.column_config.LinkColumn("Link", display_text="open")} \
        if sources else None
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config=configuration, key=f"{key}_table")


def _live(symbol: str) -> None:
    loaded = context.attempt(context.news, symbol)
    if not loaded.ok:
        st.error(layout.markdown_safe(f"Could not fetch headlines for {symbol}: {loaded.error}"))
        return
    stories = loaded.value
    if not stories:
        st.info(f"Yahoo Finance has no recent headlines for {symbol}.")
        return

    headlines = [feed_module.Headline(date=story.day, ticker=symbol, text=story.title)
                 for story in stories]
    sentiment = score_headlines(headlines)[symbol]
    st.caption(f"{len(headlines)} recent Yahoo Finance headlines for {symbol}. Yahoo's feed "
               "for a ticker can include broader market stories.")
    _detail(sentiment, headlines, "sent_live", stories)


def _feed(symbol: str, upload) -> None:
    try:
        if upload is None:
            headlines, source = feed_module.sample(), "the sample feed"
        else:
            headlines = feed_module.parse(upload.getvalue().decode("utf-8"), upload.name)
            source = upload.name
    except (ValueError, UnicodeDecodeError) as exc:
        st.error(layout.markdown_safe(f"Could not read the feed: {exc}"))
        return
    if not headlines:
        st.warning("That feed has no headlines.")
        return

    sentiments = score_headlines(headlines)
    st.caption(f"{len(headlines)} headlines across {len(sentiments)} tickers · {source}")

    table = pd.DataFrame([
        {"Ticker": ticker, "Sentiment": s.label, "Score": round(s.mean, 3),
         "Momentum": f"{s.momentum:+.3f} ({s.momentum_word})", "Confidence": s.confidence,
         "Bullish": s.counts["bullish"], "Neutral": s.counts["neutral"],
         "Bearish": s.counts["bearish"], "Headlines": len(s.scores)}
        for ticker, s in sorted(sentiments.items())])

    left, right = st.columns([3, 2])
    with left:
        st.dataframe(table, hide_index=True, width="stretch", key="sent_feed_table")
    with right:
        st.plotly_chart(sentiment_charts.ticker_scores(
            list(table["Ticker"]), list(table["Score"]), list(table["Sentiment"])),
            width="stretch", key="sent_feed_bars")

    st.subheader("Ticker detail")
    tickers = sorted(sentiments)
    if symbol not in tickers:
        st.caption(f"{symbol} is not in this feed; pick one of its tickers.")
    chosen = st.selectbox("Ticker", tickers, key="sentiment_ticker",
                          index=tickers.index(symbol) if symbol in tickers else 0)
    _detail(sentiments[chosen], feed_module.for_ticker(headlines, chosen), "sent_feed")


def render() -> None:
    symbol = context.ticker()
    layout.page_header("News Sentiment",
                       "Finance-tuned lexicon scoring of headlines, from -1 (bearish) to "
                       "+1 (bullish). It measures how the news reads, not where the price "
                       "is going.")

    _headline_scorer()
    st.divider()

    options = [f"Live news · {symbol}", "Sample feed", "Upload feed"]
    source = st.segmented_control("Headlines", options, default=options[0],
                                  key=f"sentiment_source_{symbol}")
    if source is None or source.startswith("Live"):
        st.subheader(f"{symbol} in the news")
        _live(symbol)
        return

    upload = None
    if source == "Upload feed":
        upload = st.file_uploader("Feed file: one `YYYY-MM-DD | TICKER | headline` per line",
                                  type=["txt"], key="sentiment_upload")
        if upload is None:
            st.info("Upload a feed file to score it.")
            return
    st.subheader("Feed")
    _feed(symbol, upload)
