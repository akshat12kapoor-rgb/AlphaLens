"""Strategy Backtester: test a strategy on history before trading it."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from alphalens.backtest import engine, sweep
from alphalens.charts import portfolio as portfolio_charts
from alphalens.core.config import DEFAULT_COMMISSION, DEFAULT_SLIPPAGE, INITIAL_CAPITAL
from alphalens.core.currency import money
from alphalens.data import csv_prices
from alphalens.data.models import DataUnavailable
from alphalens.signals.strategies import BENCHMARK, Context, STRATEGIES, TRADEABLE, get
from alphalens.ui import context, layout

SOURCES = ["Active ticker", "Sample data", "Upload CSV"]
PERIODS = ["1y", "2y", "5y", "10y"]
SWEEP_VALUES = {"fast": [5, 10, 15, 20, 30, 40, 50], "slow": [50, 75, 100, 150, 200]}


def _load(source: str, symbol: str, period: str, upload):
    """(frame, symbol, currency) for the chosen source."""
    if source == "Active ticker":
        return context.prices(symbol, period, "1d"), symbol, context.currency_of(symbol)
    if source == "Sample data":
        frame, name = csv_prices.sample_prices()
        return frame, name, "USD"
    if upload is None:
        return None, "", "USD"
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "prices.csv"
        path.write_bytes(upload.getvalue())
        try:
            frame, name = csv_prices.load_prices(path, symbol=upload.name.rsplit(".", 1)[0].upper())
        except DataUnavailable as exc:
            raise DataUnavailable(str(exc).replace(str(path), upload.name)) from None
    return frame, name, "USD"


def _settings():
    with st.sidebar:
        st.subheader("Backtest")
        source = st.radio("Data", SOURCES, key="bt_source", horizontal=True)
        period = st.select_slider("History", PERIODS, value="2y", key="bt_period") \
            if source == "Active ticker" else "2y"
        upload = st.file_uploader("OHLCV CSV (Date,Open,High,Low,Close,Volume)",
                                  type=["csv"], key="bt_upload") \
            if source == "Upload CSV" else None

        keys = TRADEABLE
        key = st.selectbox("Strategy", keys, format_func=lambda k: STRATEGIES[k].name,
                           key="bt_strategy")
        strategy = get(key)
        st.caption(strategy.summary)
        params = {}
        if strategy.parameters:
            columns = st.columns(len(strategy.parameters))
            for column, parameter in zip(columns, strategy.parameters):
                # Namespaced by strategy, not just page: two strategies reusing
                # a parameter name (e.g. another "fast"/"slow" pair) would
                # otherwise inherit each other's leftover session_state value
                # instead of their own default.
                params[parameter.key] = column.number_input(
                    parameter.label, parameter.minimum, parameter.maximum,
                    parameter.default, key=f"bt_param_{key}_{parameter.key}")
        layout.strategy_help(strategy)

        allow_short = st.toggle("Allow short positions", value=False, key="bt_short")
        capital = st.number_input("Starting capital", 1_000.0, 100_000_000.0,
                                  float(INITIAL_CAPITAL), 10_000.0, key="bt_capital")
        cost_bps = st.number_input("Cost per trade (bps of notional)", 0.0, 100.0,
                                   DEFAULT_COMMISSION * 10_000, 1.0, key="bt_cost")
        slippage_bps = st.number_input("Slippage (bps of notional)", 0.0, 100.0,
                                       DEFAULT_SLIPPAGE * 10_000, 1.0, key="bt_slippage",
                                       help="Price impact and spread the commission line "
                                            "above doesn't cover. Zero assumes a fill at "
                                            "exactly the close, which no real order gets - "
                                            "try 5-10 bps to see how much that assumption "
                                            "is worth.")
    return (source, period, upload, strategy, params, allow_short, capital,
            cost_bps / 10_000, slippage_bps / 10_000)


def _sweep_section(frame, strategy, params, allow_short, commission, slippage, context_) -> None:
    if not strategy.parameters:
        return
    with st.expander("Parameter sweep"):
        grid_values = {}
        columns = st.columns(len(strategy.parameters))
        for column, parameter in zip(columns, strategy.parameters):
            options = SWEEP_VALUES.get(parameter.key)
            if options is None:
                span = max(1, (parameter.maximum - parameter.minimum) // 8)
                options = list(range(parameter.minimum, parameter.maximum + 1, span))[:8]
            grid_values[parameter.key] = column.multiselect(
                parameter.label, options,
                default=[v for v in options if parameter.minimum <= v <= parameter.maximum][:5],
                key=f"bt_sweep_{strategy.key}_{parameter.key}")
        if not all(grid_values.values()):
            st.info("Pick at least one value for each parameter.")
            return
        grid = sweep.grid(frame, strategy, grid_values, allow_short=allow_short,
                          commission=commission, slippage=slippage, context=context_)
        if grid.empty:
            st.info("No valid combinations in that grid.")
            return
        keys = list(grid_values)
        if len(keys) == 2:
            st.plotly_chart(portfolio_charts.sweep_heatmap(grid, x=keys[1], y=keys[0]),
                            width="stretch", key="bt_sweep_chart")
        else:
            st.dataframe(grid.round(3), hide_index=True, width="stretch", key="bt_sweep_table")
        top = sweep.best(grid)
        st.caption(f"Best in sample: " +
                   ", ".join(f"{k} {int(top[k])}" for k in keys) +
                   f" · Sharpe {top['sharpe']:.2f} · return {top['total_return']:+.1%}. "
                   + sweep.WARNING)


def render() -> None:
    symbol = context.ticker()
    layout.page_header("Strategy Backtester",
                       "Test a strategy on history before you trade it. Positions are fully "
                       "invested (long, flat or short); a signal on one close is traded over "
                       "the next bar.")

    (source, period, upload, strategy, params, allow_short, capital,
     commission, slippage) = _settings()

    try:
        frame, name, currency = _load(source, symbol, period, upload)
    except Exception as exc:  # noqa: BLE001
        st.error(layout.markdown_safe(f"Could not load prices: {exc}"))
        return
    if frame is None:
        st.info("Upload a CSV with a `Date,Open,High,Low,Close,Volume` header to backtest it.")
        return

    detections = Context.for_frame(frame)
    try:
        result = engine.run_strategy(frame, strategy, symbol=name, currency=currency,
                                     allow_short=allow_short, capital=capital,
                                     commission=commission, slippage=slippage,
                                     context=detections, **params)
    except ValueError as exc:
        st.warning(str(exc))
        return
    benchmark = engine.run_strategy(frame, get(BENCHMARK), symbol=name, currency=currency,
                                    capital=capital, commission=commission,
                                    slippage=slippage, context=detections)

    st.markdown(f"### {result.strategy} on {name}")
    st.caption(f"{str(result.dates[0])[:10]} → {str(result.dates[-1])[:10]} · "
               f"{len(frame)} daily bars")

    columns = st.columns(5)
    layout.metric(columns[0], "Total return", f"{result.total_return:+.2%}",
                  f"{result.total_return - benchmark.total_return:+.2%} vs buy & hold")
    layout.metric(columns[1], "CAGR", f"{result.cagr:+.2%}")
    layout.metric(columns[2], "Sharpe", f"{result.sharpe:.2f}",
                  f"{result.sharpe - benchmark.sharpe:+.2f} vs buy & hold")
    layout.metric(columns[3], "Max drawdown", f"{result.max_drawdown:.2%}",
                  f"{result.max_drawdown - benchmark.max_drawdown:+.2%} vs buy & hold")
    layout.metric(columns[4], "Trades", str(result.trades),
                  f"{result.exposure:.0%} in market", delta_color="off", delta_arrow="off")

    if result.unrealized_entry_cost > 0:
        st.caption(f"⚠ The strategy still holds a position of {result.final_position:+.2f} "
                   f"on the last bar. Unwinding it would cost about "
                   f"{money(result.unrealized_entry_cost, currency)}, not reflected above - "
                   f"there's no bar after the data ends to charge it against.")

    st.plotly_chart(portfolio_charts.backtest_result(result, benchmark), width="stretch",
                    key="bt_equity")

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(portfolio_charts.positions(frame, result.positions, currency),
                        width="stretch", key="bt_positions")
    with right:
        rows = []
        for label, ours in result.metrics().items():
            theirs = benchmark.metrics()[label]
            if label == "Final equity":
                render = lambda v: money(v, currency, 0)  # noqa: E731
            elif label == "Trades":
                render = lambda v: f"{int(v)}"  # noqa: E731
            elif label == "Sharpe":
                render = lambda v: f"{v:.2f}"  # noqa: E731
            else:
                render = lambda v: f"{v:+.2%}"  # noqa: E731
            rows.append({"Metric": label, "Strategy": render(ours), "Buy & hold": render(theirs)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", key="bt_metrics")

    if source == "Active ticker":
        if st.button(f"▶ Replay {symbol} with {strategy.name} in the Trading Simulator",
                     type="primary", key="bt_handoff"):
            st.session_state[context.SIM_REQUEST_KEY] = {
                "symbol": symbol, "strategy": strategy.key, "params": params,
                "period": period if period in ("1y", "2y") else "5y"}
            st.switch_page("views/simulator.py")
        st.caption("The simulator replays the same signals candle by candle, sizing each "
                   "trade as a share of cash, so its P&L differs from this fully invested "
                   "backtest.")

    _sweep_section(frame, strategy, params, allow_short, commission, slippage, detections)
