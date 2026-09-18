"""Strategy Backtester page: AlgoBacktester's engine over any AlphaOS strategy."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from shell import context, market
from shell import strategy_lab as lab

SIM_REQUEST_KEY = "alphaos_sim_request"
PERIODS = ["1y", "2y", "5y", "10y"]
SOURCES = ["Active ticker", "Sample data", "Upload CSV"]
GREEN, RED, BLUE, GREY = "#00C853", "#FF5252", "#4A90E2", "#8892A4"


def _pct(v: float) -> str:
    return f"{v:+.2%}"


def _load_series(source: str, symbol: str, period: str, upload):
    if source == "Active ticker":
        df = market.price_history(symbol, period=period, interval="1d")
        return lab.series_from_frame(df, symbol), market.currency_symbol(symbol)
    if source == "Sample data":
        return lab.load_sample(), "$"
    if upload is None:
        return None, "$"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prices.csv"
        path.write_bytes(upload.getvalue())
        try:
            return lab.load_upload(path, upload.name), "$"
        except ValueError as exc:
            raise ValueError(str(exc).replace(str(path), upload.name)) from None


def _results_chart(run: lab.LabRun, cur: str) -> go.Figure:
    r, b = run.result, run.benchmark
    dates = r.dates
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28],
                        vertical_spacing=0.04)
    fig.add_trace(go.Scatter(x=dates, y=b.equity, name="Buy & hold",
                             line=dict(color=GREY, width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=r.equity, name=r.strategy,
                             line=dict(color=BLUE, width=2.2)), row=1, col=1)
    for eq, color, name in ((r.equity, BLUE, "Strategy drawdown"),
                            (b.equity, GREY, "Buy & hold drawdown")):
        s = pd.Series(eq)
        dd = s / s.cummax() - 1
        fig.add_trace(go.Scatter(x=dates, y=dd, name=name, line=dict(color=color, width=1),
                                 fill="tozeroy" if color == BLUE else None,
                                 showlegend=False), row=2, col=1)
    fig.update_yaxes(title_text=f"equity ({cur})", row=1, col=1)
    fig.update_yaxes(title_text="drawdown", tickformat=".0%", row=2, col=1)
    fig.update_layout(template="plotly_dark", height=520, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.08, x=0), hovermode="x unified")
    return fig


def _positions_chart(series, positions: list[float], cur: str) -> go.Figure:
    dates, closes = series.dates, series.closes
    fig = go.Figure(go.Scatter(x=dates, y=closes, name="Close", line=dict(color="#E6E9EF", width=1.3)))
    previous = 0.0
    entries = {"long": ([], []), "short": ([], []), "flat": ([], [])}
    for d, c, p in zip(dates, closes, positions):
        if p != previous:
            side = "long" if p > 0 else "short" if p < 0 else "flat"
            entries[side][0].append(d)
            entries[side][1].append(c)
        previous = p
    for side, marker, color in (("long", "triangle-up", GREEN), ("short", "triangle-down", RED),
                                ("flat", "x", GREY)):
        xs, ys = entries[side]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name=f"→ {side}",
                                     marker=dict(symbol=marker, size=10, color=color)))
    fig.update_yaxes(title_text=f"price ({cur})")
    fig.update_layout(template="plotly_dark", height=360, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.12, x=0))
    return fig


def _sweep_section(series, allow_short: bool, commission: float) -> None:
    with st.expander("Parameter sweep: SMA fast × slow"):
        c1, c2 = st.columns(2)
        fasts = c1.multiselect("Fast windows", [5, 10, 15, 20, 30, 40, 50],
                               default=[5, 10, 20, 30, 50], key="bt_sweep_fast")
        slows = c2.multiselect("Slow windows", [50, 75, 100, 150, 200],
                               default=[50, 100, 150, 200], key="bt_sweep_slow")
        grid = lab.sweep(series, sorted(fasts), sorted(slows),
                         allow_short=allow_short, commission=commission)
        if grid.empty:
            st.info("Pick at least one fast window smaller than a slow window.")
            return
        pivot = grid.pivot(index="fast", columns="slow", values="sharpe")
        fig = go.Figure(go.Heatmap(
            z=pivot.values, x=[str(c) for c in pivot.columns], y=[str(i) for i in pivot.index],
            colorscale="RdYlGn", zmid=0, text=pivot.round(2).values,
            texttemplate="%{text}", colorbar=dict(title="Sharpe")))
        fig.update_xaxes(title_text="slow SMA"); fig.update_yaxes(title_text="fast SMA")
        fig.update_layout(template="plotly_dark", height=320, paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="bt_sweep_chart")
        best = grid.loc[grid["sharpe"].idxmax()]
        st.caption(f"Best in-sample: SMA {int(best.fast)}/{int(best.slow)} · Sharpe "
                   f"{best.sharpe:.2f} · return {best.total_return:+.1%}. The best cell of a sweep "
                   "is the most fitted to this history, not a forecast - check it on another "
                   "period or ticker before trusting it.")


def render() -> None:
    symbol = context.ticker()
    st.title("Strategy Backtester")
    st.caption("Test a strategy on history before you trade it. Positions are fully "
               "invested (long, flat or short); a signal on one close is traded over the next bar.")

    with st.sidebar:
        st.subheader("Backtest setup")
        source = st.radio("Data", SOURCES, key="bt_source", horizontal=True)
        period, upload = "2y", None
        if source == "Active ticker":
            period = st.select_slider("History", PERIODS, value="2y", key="bt_period")
        elif source == "Upload CSV":
            upload = st.file_uploader("OHLCV CSV (Date,Open,High,Low,Close,Volume)",
                                      type=["csv"], key="bt_upload")
        name = st.selectbox("Strategy", lab.CATALOGUE, key="bt_strategy")
        st.caption(lab.DESCRIPTIONS[name])
        fast, slow = 20, 50
        if name == lab.SMA_CROSSOVER:
            c1, c2 = st.columns(2)
            fast = c1.number_input("Fast SMA", 2, 200, 20, key="bt_fast")
            slow = c2.number_input("Slow SMA", 3, 400, 50, key="bt_slow")
        allow_short = st.toggle("Allow short positions", value=False, key="bt_short")
        capital = st.number_input("Starting capital", 1_000.0, 100_000_000.0, 100_000.0,
                                  step=10_000.0, key="bt_capital")
        commission_bps = st.number_input("Cost per trade (bps of notional)", 0.0, 100.0, 5.0,
                                         step=1.0, key="bt_cost")
    commission = commission_bps / 10_000

    try:
        series, cur = _load_series(source, symbol, period, upload)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load prices: {exc}")
        return
    if series is None:
        st.info("Upload a CSV with a `Date,Open,High,Low,Close,Volume` header to backtest it.")
        return
    if name == lab.SMA_CROSSOVER and fast >= slow:
        st.warning("The fast SMA window must be shorter than the slow one.")
        return

    try:
        run = lab.run(series, name, allow_short=allow_short, capital=capital,
                      commission=commission, fast=int(fast), slow=int(slow))
    except ValueError as exc:
        st.error(str(exc))
        return
    r, b = run.result, run.benchmark

    st.subheader(f"{r.strategy} on {series.symbol}")
    st.caption(f"{r.dates[0]} → {r.dates[-1]} · {len(series)} daily bars")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total return", _pct(r.total_return), f"{r.total_return - b.total_return:+.2%} vs buy & hold")
    k2.metric("CAGR", _pct(r.cagr))
    k3.metric("Sharpe", f"{r.sharpe:.2f}", f"{r.sharpe - b.sharpe:+.2f} vs buy & hold")
    k4.metric("Max drawdown", f"{r.max_drawdown:.2%}",
              f"{r.max_drawdown - b.max_drawdown:+.2%} vs buy & hold")
    k5.metric("Trades", f"{r.trades}", f"{r.exposure:.0%} time in market", delta_color="off",
              delta_arrow="off")

    st.plotly_chart(_results_chart(run, cur), width="stretch", key="bt_equity_chart")

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(_positions_chart(series, run.positions, cur), width="stretch",
                        key="bt_positions_chart")
    with right:
        sm, bm = lab.metrics(r), lab.metrics(b)
        rows = []
        for key in sm:
            fmt = (lambda v: f"{cur}{v:,.0f}") if key == "Final equity" else \
                  (lambda v: str(v)) if key == "Trades" else \
                  (lambda v: f"{v:.2f}") if key == "Sharpe" else (lambda v: f"{v:+.2%}")
            rows.append({"Metric": key, "Strategy": fmt(sm[key]), "Buy & hold": fmt(bm[key])})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", key="bt_metrics")

    equivalent = lab.simulator_equivalent(name, int(fast), int(slow))
    if source == "Active ticker" and equivalent:
        if st.button(f"▶ Replay {symbol} with {equivalent} in the Trading Simulator",
                     type="primary", key="bt_handoff"):
            st.session_state[SIM_REQUEST_KEY] = {
                "ticker": symbol, "strategy": equivalent, "interval": "1d",
                "period": period if period in ("1y", "2y") else "5y",
            }
            st.switch_page("views/simulator.py")
        st.caption("The simulator replays the same signals candle by candle, sizing each "
                   "trade at 10% of cash, so its P&L differs from this fully-invested backtest.")

    if name == lab.SMA_CROSSOVER:
        _sweep_section(series, allow_short, commission)
