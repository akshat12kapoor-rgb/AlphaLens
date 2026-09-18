"""
AlphaOS overview: the active ticker through every tool at once.

Each card is computed with the same code its tool uses (and the valuation card
with the valuation page's default assumptions), so the numbers here match what
you see when you open the tool.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shell import context, market
from shell import strategy_lab as lab

PAGES = {
    "backtest": "views/backtester.py",
    "simulator": "views/simulator.py",
    "valuation": "views/valuation.py",
    "sentiment": "views/sentiment.py",
}


def _unavailable(snapshot) -> None:
    st.caption(f"Unavailable: {snapshot.error}")


def _header(symbol: str, history, profile, cur: str) -> None:
    name = profile.value.get("company_name") if profile.ok else None
    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"## {name or symbol} `{symbol}`")
        if profile.ok and profile.value.get("sector"):
            st.caption(f"{profile.value['sector']} · {profile.value.get('industry') or ''}")
    if not history.ok:
        with right:
            _unavailable(history)
        return
    close = history.value["close"]
    last, prev = float(close.iloc[-1]), float(close.iloc[-2])
    year = close[close.index >= close.index[-1] - pd.Timedelta(days=365)]
    with right:
        c1, c2 = st.columns(2)
        c1.metric("Last close", f"{cur}{last:,.2f}", f"{last / prev - 1:+.2%} on the day")
        c2.metric("1-year return", f"{last / float(year.iloc[0]) - 1:+.1%}",
                  market.md(f"52-week range {cur}{year.min():,.0f}–{cur}{year.max():,.0f}"),
                  delta_color="off", delta_arrow="off")


def _price_chart(history, cur: str) -> None:
    if not history.ok:
        return
    df = history.value.iloc[-252:]
    sma50 = history.value["close"].rolling(50).mean().iloc[-252:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["close"], name="Close",
                             line=dict(color="#4A90E2", width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=sma50, name="SMA 50",
                             line=dict(color="#FFB020", width=1.2, dash="dot")))
    fig.update_layout(template="plotly_dark", height=260, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.1, x=0), yaxis_title=cur)
    st.plotly_chart(fig, width="stretch", key="overview_price")


def _card(title: str, blurb: str, page: str, link: str, icon: str):
    box = st.container(border=True, height="stretch")
    with box:
        st.markdown(f"#### {title}")
        st.caption(blurb)
    return box, (page, link, icon)


def _link(box, target) -> None:
    page, label, icon = target
    with box:
        st.page_link(page, label=label, icon=icon)


def _valuation_card(profile, cur: str) -> None:
    box, target = _card("Valuation", "DCF + comparables, default assumptions",
                        PAGES["valuation"], "Open valuation", ":material/calculate:")
    with box:
        if not profile.ok:
            _unavailable(profile)
        else:
            verdict = market.attempt(market.default_valuation, profile.value)
            if not verdict.ok:
                _unavailable(verdict)
            else:
                v = verdict.value
                st.metric("Valuation signal", f"{v.emoji} {v.decision}",
                          f"{v.upside_pct:+.1%} upside to fair value")
                st.caption(market.md(f"Fair value {cur}{v.blended_value:,.2f} · "
                                     f"price {cur}{v.current_price:,.2f}"))
    _link(box, target)


def _backtest_card(symbol: str, history) -> None:
    box, target = _card("Backtest", "SMA 20/50 crossover, last 2 years",
                        PAGES["backtest"], "Backtest strategies", ":material/query_stats:")
    with box:
        if not history.ok:
            _unavailable(history)
        else:
            run = market.attempt(lambda: lab.run(lab.series_from_frame(history.value, symbol),
                                                 lab.SMA_CROSSOVER))
            if not run.ok:
                _unavailable(run)
            else:
                r, b = run.value.result, run.value.benchmark
                st.metric("SMA 20/50 return", f"{r.total_return:+.1%}",
                          f"{r.total_return - b.total_return:+.1%} vs buy & hold")
                st.caption(f"Sharpe {r.sharpe:.2f} (buy & hold {b.sharpe:.2f}) · "
                           f"max drawdown {r.max_drawdown:.1%} · {r.trades} trades")
    _link(box, target)


def _simulator_card(history) -> None:
    box, target = _card("Trading simulator", "Where the technicals stand today",
                        PAGES["simulator"], "Trade it in simulation", ":material/candlestick_chart:")
    with box:
        if not history.ok:
            _unavailable(history)
        else:
            snap = market.attempt(_technicals, history.value)
            if not snap.ok:
                _unavailable(snap)
            else:
                t = snap.value
                st.metric("RSI (14)", f"{t['rsi']:.0f}", t["rsi_zone"], delta_color="off",
                          delta_arrow="off")
                st.caption(f"SMA 20 {'above' if t['uptrend'] else 'below'} SMA 50 "
                           f"({'uptrend' if t['uptrend'] else 'downtrend'}) · {t['last_signal']}")
    _link(box, target)


def _technicals(df: pd.DataFrame) -> dict:
    enriched = market.surfaces.module(market.surfaces.SIMULATOR, "indicators").calculate_all_indicators(df)
    rsi = float(enriched["rsi"].iloc[-1])
    zone = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral"
    latest = []
    for name in ("RSI Strategy", "MACD Strategy", "MA Crossover"):
        signals = lab.simulator_signals(df, name)
        for bars_ago, signal in enumerate(reversed(signals)):
            if signal != "HOLD":
                latest.append((bars_ago, name.replace(" Strategy", ""), signal))
                break
    if latest:
        bars_ago, name, signal = min(latest)
        last_signal = f"latest signal: {name} {signal}, {bars_ago} bar{'s' if bars_ago != 1 else ''} ago"
    else:
        last_signal = "no recent signals"
    return {"rsi": rsi, "rsi_zone": zone,
            "uptrend": bool(enriched["sma_20"].iloc[-1] > enriched["sma_50"].iloc[-1]),
            "last_signal": last_signal}


def _sentiment_card(symbol: str) -> None:
    box, target = _card("News sentiment", "Recent Yahoo Finance headlines",
                        PAGES["sentiment"], "Read the news", ":material/newspaper:")
    with box:
        from shell import sentiment_page
        from sentiment import score_headlines

        loaded = market.attempt(sentiment_page.live_headlines, symbol)
        if not loaded.ok:
            _unavailable(loaded)
        elif not loaded.value[0]:
            st.caption(f"No recent headlines for {symbol}.")
        else:
            s = score_headlines(loaded.value[0])[symbol]
            st.metric("News sentiment", s.label, f"{s.mean:+.3f} average score")
            st.caption(f"{len(s.scores)} headlines · confidence {s.confidence} · "
                       f"momentum {sentiment_page.momentum_word(s.momentum)}")
    _link(box, target)


def render() -> None:
    symbol = context.ticker()
    cur = market.currency_symbol(symbol)

    st.title("AlphaOS")
    st.markdown("**The financial analysis and trading simulation platform.** Value a company, "
                "read its news, backtest a strategy on its history, then trade it candle by "
                "candle in simulation - all on one ticker, in one place.")

    with st.spinner(f"Loading {symbol}…"):
        history = market.attempt(market.price_history, symbol, "2y", "1d")
        profile = market.attempt(market.fundamentals, symbol)

    _header(symbol, history, profile, cur)
    _price_chart(history, cur)

    row = st.columns(4)
    with row[0]:
        _valuation_card(profile, cur)
    with row[1]:
        _sentiment_card(symbol)
    with row[2]:
        _backtest_card(symbol, history)
    with row[3]:
        _simulator_card(history)

    st.caption("Market data and news from Yahoo Finance, which can be delayed or rate-limited. "
               "AlphaOS is for research, learning and simulation - it is not financial advice "
               "and places no real trades.")
