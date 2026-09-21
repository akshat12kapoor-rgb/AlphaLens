"""Overview: the active ticker through every tool at once."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from alphalens.backtest import engine
from alphalens.charts import theme
from alphalens.core.currency import money
from alphalens.sentiment import feed as feed_module
from alphalens.sentiment.scoring import score_headlines
from alphalens.signals import indicators
from alphalens.signals.strategies import Context, get
from alphalens.ui import context, layout
from alphalens.valuation.analysis import value

import plotly.graph_objects as go

PAGES = {"valuation": "views/valuation.py", "sentiment": "views/sentiment.py",
         "backtester": "views/backtester.py", "simulator": "views/simulator.py"}


@dataclass(frozen=True)
class Read:
    """One card's take, reduced to a direction for the synthesis line below
    them. `lean` is "bullish"/"bearish"/"neutral" for the three tools that
    actually read on the stock's direction, or "context" for the backtest,
    which measures whether trend-following works on this history - a
    different question from which way the stock is headed."""

    name: str
    lean: str
    detail: str


def _header(symbol: str, history, profile, currency: str) -> None:
    left, right = st.columns([3, 2])
    with left:
        name = profile.value.name if profile.ok else symbol
        st.markdown(f"## {name} `{symbol}`")
        if profile.ok and profile.value.sector:
            st.caption(" · ".join(filter(None, [profile.value.sector, profile.value.industry])))
    if not history.ok:
        with right:
            layout.unavailable(history, "Prices")
        return
    closes = history.value["close"]
    last, previous = float(closes.iloc[-1]), float(closes.iloc[-2])
    year = closes[closes.index >= closes.index[-1] - pd.Timedelta(days=365)]
    with right:
        columns = st.columns(2)
        layout.metric(columns[0], "Last close", money(last, currency),
                      f"{last / previous - 1:+.2%} on the day")
        layout.metric(columns[1], "1-year return", f"{last / float(year.iloc[0]) - 1:+.1%}",
                      f"52-week range {money(year.min(), currency, 0)}–"
                      f"{money(year.max(), currency, 0)}",
                      delta_color="off", delta_arrow="off")


def _price_chart(history, currency: str) -> None:
    if not history.ok:
        return
    frame = history.value.iloc[-252:]
    average = history.value["close"].rolling(50).mean().iloc[-252:]
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=frame.index, y=frame["close"], name="Close",
                                line=dict(color=theme.ACCENT, width=2)))
    figure.add_trace(go.Scatter(x=average.index, y=average, name="SMA 50",
                                line=dict(color=theme.GOLD, width=1.2, dash="dot")))
    st.plotly_chart(theme.apply(figure, height=260), width="stretch", key="overview_price")


def _card(title: str, blurb: str):
    box = st.container(border=True, height="stretch")
    with box:
        st.markdown(f"#### {title}")
        st.caption(blurb)
    return box


def _valuation_card(profile, currency: str) -> Read | None:
    box = _card("Valuation", "DCF and comparables, default assumptions")
    read = None
    with box:
        if not profile.ok:
            layout.unavailable(profile)
        else:
            valued = context.attempt(value, profile.value)
            if not valued.ok:
                layout.unavailable(valued)
            else:
                verdict = valued.value.verdict
                layout.metric(st, "Valuation signal", verdict.label,
                              f"{verdict.upside:+.1%} upside to fair value")
                st.caption(layout.markdown_safe(
                    f"Fair value {money(verdict.fair_value, currency)} · "
                    f"price {money(verdict.current_price, currency)}"))
                lean = ("bullish" if verdict.decision == "BUY"
                        else "bearish" if verdict.decision == "SELL" else "neutral")
                read = Read("Valuation", lean,
                            f"says {verdict.decision} ({verdict.upside:+.1%} to fair value)")
        st.page_link(PAGES["valuation"], label="Open valuation", icon=":material/calculate:")
    return read


def _sentiment_card(symbol: str) -> Read | None:
    box = _card("News sentiment", "Recent Yahoo Finance headlines")
    read = None
    with box:
        stories = context.attempt(context.news, symbol)
        if not stories.ok:
            layout.unavailable(stories)
        elif not stories.value:
            st.caption(f"No recent headlines for {symbol}.")
        else:
            headlines = [feed_module.Headline(date=s.day, ticker=symbol, text=s.title)
                         for s in stories.value]
            sentiment = score_headlines(headlines)[symbol]
            layout.metric(st, "News sentiment", sentiment.label,
                          f"{sentiment.mean:+.3f} average score")
            st.caption(f"{len(sentiment.scores)} headlines · confidence "
                       f"{sentiment.confidence} · momentum {sentiment.momentum_word}")
            lean = ("bullish" if sentiment.label == "BULLISH"
                    else "bearish" if sentiment.label == "BEARISH" else "neutral")
            read = Read("Sentiment", lean, f"reads {sentiment.label.lower()} "
                                           f"({sentiment.mean:+.2f})")
        st.page_link(PAGES["sentiment"], label="Read the news", icon=":material/newspaper:")
    return read


def _backtest_card(symbol: str, history, currency: str) -> Read | None:
    box = _card("Backtest", "MA crossover 20/50, last 2 years")
    read = None
    with box:
        if not history.ok:
            layout.unavailable(history)
        else:
            strategy = get("ma_crossover")
            run = context.attempt(engine.run_strategy, history.value, strategy,
                                  symbol=symbol, currency=currency)
            benchmark = context.attempt(engine.run_strategy, history.value,
                                        get("buy_and_hold"), symbol=symbol, currency=currency)
            if not run.ok or not benchmark.ok:
                layout.unavailable(run if not run.ok else benchmark)
            else:
                result, hold = run.value, benchmark.value
                edge = result.total_return - hold.total_return
                layout.metric(st, "MA 20/50 return", f"{result.total_return:+.1%}",
                              f"{edge:+.1%} vs buy & hold")
                st.caption(f"Sharpe {result.sharpe:.2f} (buy & hold {hold.sharpe:.2f}) · "
                           f"max drawdown {result.max_drawdown:.1%} · {result.trades} trades")
                verb = "beating" if edge > 0 else "lagging" if edge < 0 else "matching"
                read = Read("Backtest", "context", f"has trend-following {verb} buy & hold")
        st.page_link(PAGES["backtester"], label="Backtest strategies",
                     icon=":material/query_stats:")
    return read


def _technicals(frame: pd.DataFrame) -> dict:
    enriched = indicators.enrich(frame)
    detections = Context.for_frame(enriched)
    strength = float(enriched["rsi"].iloc[-1])
    latest = []
    for key in ("rsi", "macd", "ma_crossover"):
        signals = get(key).signals(enriched, detections)
        for bars_ago, signal in enumerate(reversed(list(signals))):
            if signal != "HOLD":
                latest.append((bars_ago, get(key).name, signal))
                break
    if latest:
        bars_ago, name, signal = min(latest)
        recent = (f"latest signal: {name} {signal}, {bars_ago} "
                  f"bar{'s' if bars_ago != 1 else ''} ago")
    else:
        recent = "no recent signals"
    return {"rsi": strength,
            "zone": "overbought" if strength > 70 else "oversold" if strength < 30 else "neutral",
            "uptrend": bool(enriched["sma_20"].iloc[-1] > enriched["sma_50"].iloc[-1]),
            "recent": recent}


def _simulator_card(history) -> Read | None:
    box = _card("Trading simulator", "Where the technicals stand today")
    read = None
    with box:
        if not history.ok:
            layout.unavailable(history)
        else:
            attempt = context.attempt(_technicals, history.value)
            if not attempt.ok:
                layout.unavailable(attempt)
            else:
                signals = attempt.value
                layout.metric(st, "RSI (14)", f"{signals['rsi']:.0f}", signals["zone"],
                              delta_color="off", delta_arrow="off")
                st.caption(f"SMA 20 {'above' if signals['uptrend'] else 'below'} SMA 50 "
                           f"({'uptrend' if signals['uptrend'] else 'downtrend'}) · "
                           f"{signals['recent']}")
                lean = "bullish" if signals["uptrend"] else "bearish"
                trend = "an uptrend" if signals["uptrend"] else "a downtrend"
                read = Read("Technicals", lean, f"is in {trend} (RSI {signals['zone']})")
        st.page_link(PAGES["simulator"], label="Trade it in simulation",
                     icon=":material/candlestick_chart:")
    return read


def join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def takeaway(reads: list[Read | None]) -> str | None:
    """One sentence combining several tools' reads on the same ticker.

    This is the payoff of reading one ticker through four lenses instead of
    one - without it, the cards are just four numbers that never add up to a
    single answer. Needs at least two working reads to say anything; one
    read alone isn't a synthesis, it's just that card again. Public (not
    page-private) because the Watchlist page builds the same sentence for
    tickers other than the active one.
    """
    available = [r for r in reads if r is not None]
    if len(available) < 2:
        return None

    bullish = [r.name for r in available if r.lean == "bullish"]
    bearish = [r.name for r in available if r.lean == "bearish"]
    parts = " · ".join(f"**{r.name}** {r.detail}" for r in available)

    if bullish and bearish:
        line = (f"They disagree: {join_names(bullish)} "
                f"{'leans' if len(bullish) == 1 else 'lean'} bullish, "
                f"{join_names(bearish)} {'leans' if len(bearish) == 1 else 'lean'} bearish.")
    elif bullish:
        line = (f"{join_names(bullish)} {'is' if len(bullish) == 1 else 'are'} bullish, "
                f"and nothing above contradicts it.")
    elif bearish:
        line = (f"{join_names(bearish)} {'is' if len(bearish) == 1 else 'are'} bearish, "
                f"and nothing above contradicts it.")
    else:
        line = "None of them lean strongly either way right now."
    return f"{parts}. {line}"


def _synthesis(reads: list[Read | None]) -> None:
    line = takeaway(reads)
    if line:
        st.info(layout.markdown_safe(line))


# ── pure reads, for reuse by pages other than this one (e.g. Watchlist) ─────
#
# These duplicate a few lines of what the card functions above already
# compute, rather than threading a shared helper through code that's also
# doing per-card rendering (spinners, metrics, page_links) - not worth
# entangling two pages' rendering to save a handful of near-identical lines.

def valuation_read(profile, currency: str) -> Read | None:
    if not profile.ok:
        return None
    valued = context.attempt(value, profile.value)
    if not valued.ok:
        return None
    verdict = valued.value.verdict
    lean = ("bullish" if verdict.decision == "BUY"
            else "bearish" if verdict.decision == "SELL" else "neutral")
    return Read("Valuation", lean, f"says {verdict.decision} ({verdict.upside:+.1%} to fair value)")


def sentiment_read(symbol: str) -> Read | None:
    stories = context.attempt(context.news, symbol)
    if not stories.ok or not stories.value:
        return None
    headlines = [feed_module.Headline(date=s.day, ticker=symbol, text=s.title)
                 for s in stories.value]
    sentiment = score_headlines(headlines)[symbol]
    lean = ("bullish" if sentiment.label == "BULLISH"
            else "bearish" if sentiment.label == "BEARISH" else "neutral")
    return Read("Sentiment", lean, f"reads {sentiment.label.lower()} ({sentiment.mean:+.2f})")


def backtest_read(symbol: str, history, currency: str) -> Read | None:
    if not history.ok:
        return None
    strategy = get("ma_crossover")
    run = context.attempt(engine.run_strategy, history.value, strategy,
                          symbol=symbol, currency=currency)
    benchmark = context.attempt(engine.run_strategy, history.value,
                                get("buy_and_hold"), symbol=symbol, currency=currency)
    if not run.ok or not benchmark.ok:
        return None
    edge = run.value.total_return - benchmark.value.total_return
    verb = "beating" if edge > 0 else "lagging" if edge < 0 else "matching"
    return Read("Backtest", "context", f"has trend-following {verb} buy & hold")


def technicals_read(history) -> Read | None:
    if not history.ok:
        return None
    attempt = context.attempt(_technicals, history.value)
    if not attempt.ok:
        return None
    signals = attempt.value
    lean = "bullish" if signals["uptrend"] else "bearish"
    trend = "an uptrend" if signals["uptrend"] else "a downtrend"
    return Read("Technicals", lean, f"is in {trend} (RSI {signals['zone']})")


def gather_reads(symbol: str) -> list[Read | None]:
    """Every tool's read on `symbol`, for a ticker that isn't necessarily the
    active one - one Yahoo round trip per tool, same as this page pays for
    the active ticker."""
    history = context.attempt(context.prices, symbol, "2y", "1d")
    profile = context.attempt(context.fundamentals, symbol)
    currency = profile.value.currency if profile.ok else context.currency_of(symbol)
    return [valuation_read(profile, currency), sentiment_read(symbol),
            backtest_read(symbol, history, currency), technicals_read(history)]


def export_markdown(symbol: str, name: str, history, reads: list[Read | None]) -> str:
    """A snapshot of this page as a plain-text file - the "send this to
    someone" AlphaLens otherwise has no way to produce."""
    lines = [f"# {name} ({symbol}) - AlphaLens summary",
             f"Generated {pd.Timestamp.now():%Y-%m-%d %H:%M}", ""]
    if history.ok:
        lines.append(f"Last close: {history.value['close'].iloc[-1]:,.2f}")
        lines.append("")
    for read in reads:
        if read is not None:
            lines.append(f"- **{read.name}**: {read.detail}")
    line = takeaway(reads)
    if line:
        lines += ["", "## Takeaway", line.replace("**", "")]
    lines += ["", "---",
              "Market data and news from Yahoo Finance, which can be delayed or "
              "rate-limited. Educational use only - not financial advice."]
    return "\n".join(lines)


def render() -> None:
    symbol = context.ticker()
    st.title("AlphaLens")
    st.markdown("**The financial analysis and trading simulation platform.** Value a company, "
                "read its news, backtest a strategy on its history, then trade it candle by "
                "candle in simulation — all on one ticker, in one place.")

    with st.spinner(f"Loading {symbol}…"):
        history = context.attempt(context.prices, symbol, "2y", "1d")
        profile = context.attempt(context.fundamentals, symbol)
    currency = profile.value.currency if profile.ok else context.currency_of(symbol)

    _header(symbol, history, profile, currency)
    _price_chart(history, currency)

    columns = st.columns(4)
    with columns[0]:
        card_valuation = _valuation_card(profile, currency)
    with columns[1]:
        card_sentiment = _sentiment_card(symbol)
    with columns[2]:
        card_backtest = _backtest_card(symbol, history, currency)
    with columns[3]:
        card_simulator = _simulator_card(history)

    reads = [card_valuation, card_sentiment, card_backtest, card_simulator]
    _synthesis(reads)

    name = profile.value.name if profile.ok else symbol
    st.download_button(
        "Download summary", icon=":material/download:",
        data=export_markdown(symbol, name, history, reads),
        file_name=f"{symbol}_alphalens_summary.md", mime="text/markdown",
        key="overview_export")

    st.caption("Market data and news from Yahoo Finance, which can be delayed or "
               "rate-limited. AlphaLens is for research, learning and simulation — it is not "
               "financial advice and places no real trades.")
