"""Overview: the active ticker through every tool at once."""
from __future__ import annotations

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


def _valuation_card(profile, currency: str) -> None:
    box = _card("Valuation", "DCF and comparables, default assumptions")
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
        st.page_link(PAGES["valuation"], label="Open valuation", icon=":material/calculate:")


def _sentiment_card(symbol: str) -> None:
    box = _card("News sentiment", "Recent Yahoo Finance headlines")
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
        st.page_link(PAGES["sentiment"], label="Read the news", icon=":material/newspaper:")


def _backtest_card(symbol: str, history, currency: str) -> None:
    box = _card("Backtest", "MA crossover 20/50, last 2 years")
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
                layout.metric(st, "MA 20/50 return", f"{result.total_return:+.1%}",
                              f"{result.total_return - hold.total_return:+.1%} vs buy & hold")
                st.caption(f"Sharpe {result.sharpe:.2f} (buy & hold {hold.sharpe:.2f}) · "
                           f"max drawdown {result.max_drawdown:.1%} · {result.trades} trades")
        st.page_link(PAGES["backtester"], label="Backtest strategies",
                     icon=":material/query_stats:")


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


def _simulator_card(history) -> None:
    box = _card("Trading simulator", "Where the technicals stand today")
    with box:
        if not history.ok:
            layout.unavailable(history)
        else:
            read = context.attempt(_technicals, history.value)
            if not read.ok:
                layout.unavailable(read)
            else:
                signals = read.value
                layout.metric(st, "RSI (14)", f"{signals['rsi']:.0f}", signals["zone"],
                              delta_color="off", delta_arrow="off")
                st.caption(f"SMA 20 {'above' if signals['uptrend'] else 'below'} SMA 50 "
                           f"({'uptrend' if signals['uptrend'] else 'downtrend'}) · "
                           f"{signals['recent']}")
        st.page_link(PAGES["simulator"], label="Trade it in simulation",
                     icon=":material/candlestick_chart:")


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
        _valuation_card(profile, currency)
    with columns[1]:
        _sentiment_card(symbol)
    with columns[2]:
        _backtest_card(symbol, history, currency)
    with columns[3]:
        _simulator_card(history)

    st.caption("Market data and news from Yahoo Finance, which can be delayed or "
               "rate-limited. AlphaLens is for research, learning and simulation — it is not "
               "financial advice and places no real trades.")
