"""Trading Simulator: replay real market data candle by candle and paper trade it."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from alphalens.charts import portfolio as portfolio_charts
from alphalens.charts import price as price_charts
from alphalens.core.currency import money, signed_money
from alphalens.data import yahoo
from alphalens.signals.strategies import STRATEGIES, TRADEABLE, get
from alphalens.trading import performance
from alphalens.ui import context, layout, replay

MANUAL = "manual"
CHOICES = [MANUAL, *TRADEABLE]


def label_for(key: str) -> str:
    return "Manual trading" if key == MANUAL else STRATEGIES[key].name


def render_chart(state: replay.Session, key: str) -> None:
    """The main candlestick view, drawn from the current replay position.

    Called both by the page and by the ticking fragment, so the two never
    disagree about how the chart looks.
    """
    visible = state.visible
    offset = state.visible_start
    gaps = replay.windowed_gaps(state.context.fvg if state.context else None, offset)
    options = st.session_state.get("sim_overlays", {})
    figure = price_charts.candles(
        visible, currency=state.currency,
        title=f"{state.symbol} · {label_for(state.strategy_key)}",
        signals=state.signals.iloc[offset:state.index + 1] if state.signals is not None else None,
        gaps=gaps,
        sweeps=state.context.sweeps if state.context else None,
        trades=state.engine.trades,
        show_ma=options.get("ma", True), show_rsi=options.get("rsi", True),
        show_macd=options.get("macd", False), show_gaps=options.get("gaps", False),
        show_sweeps=options.get("sweeps", False), show_signals=options.get("signals", False),
        show_trades=options.get("trades", True), current_index=len(visible) - 1)
    st.plotly_chart(figure, width="stretch", key=key)


def _sidebar(state: replay.Session, symbol: str) -> None:
    with st.sidebar:
        st.subheader("Replay")
        st.caption(f"Simulating **{symbol}** · change it with the Active ticker picker")

        columns = st.columns(2)
        intervals = ["1d", "1h", "15m", "5m"]
        interval = columns[0].selectbox("Timeframe", intervals, key="sim_interval")
        periods = yahoo.periods_for(interval)
        if st.session_state.get("sim_period") not in periods:
            st.session_state["sim_period"] = periods[min(2, len(periods) - 1)]
        period = columns[1].selectbox("Period", periods, key="sim_period")

        if st.button("Load data", width="stretch", type="primary", key="sim_fetch"):
            _load(symbol, period, interval)
            st.rerun()

        if state.loaded and state.symbol != symbol:
            st.caption(f"⚠️ Showing **{state.symbol}**. Load data to switch to **{symbol}**.")

        st.divider()
        st.subheader("Strategy")
        choice = st.radio("Strategy", CHOICES, format_func=label_for,
                          index=CHOICES.index(state.strategy_key), key="sim_strategy",
                          label_visibility="collapsed")
        params = {}
        if choice != MANUAL:
            strategy = get(choice)
            for parameter in strategy.parameters:
                # Namespaced by strategy, not just page: see the matching note
                # in ui/pages/backtester.py.
                params[parameter.key] = st.number_input(
                    parameter.label, parameter.minimum, parameter.maximum,
                    state.params.get(parameter.key, parameter.default),
                    key=f"sim_param_{choice}_{parameter.key}", help=parameter.help)
            layout.strategy_help(strategy)
        if choice != state.strategy_key or params != state.params:
            replay.set_strategy(choice, params)

        st.divider()
        st.subheader("Chart")
        overlays = {}
        left, right = st.columns(2)
        overlays["ma"] = left.toggle("Moving averages", value=True, key="sim_ov_ma")
        overlays["rsi"] = right.toggle("RSI", value=True, key="sim_ov_rsi")
        overlays["macd"] = left.toggle("MACD", value=False, key="sim_ov_macd")
        overlays["trades"] = right.toggle("Trades", value=True, key="sim_ov_trades")
        overlays["gaps"] = left.toggle("FVG zones", value=False, key="sim_ov_gaps")
        overlays["sweeps"] = right.toggle("Sweeps", value=False, key="sim_ov_sweeps")
        overlays["signals"] = left.toggle("Signals", value=False, key="sim_ov_signals")
        st.session_state["sim_overlays"] = overlays

        st.divider()
        state.learning = st.toggle(
            "Learning Mode", value=state.learning, key="sim_learning",
            help="Pause at every signal, gap and sweep, and call the next move "
                 "before seeing what happened.")

        if state.loaded and state.strategy_key == MANUAL:
            st.divider()
            st.subheader("Trade")
            buy, sell = st.columns(2)
            if buy.button("BUY", width="stretch", key="sim_buy"):
                _trade("buy", state)
            if sell.button("SELL", width="stretch", key="sim_sell"):
                _trade("sell", state)
            st.caption(f"Holdings: {state.engine.holdings:+d} · "
                       f"cash {money(state.engine.balance, state.currency, 0)}")

        if state.loaded and st.button("Reset portfolio", width="stretch", key="sim_reset"):
            replay.reset_account()
            st.rerun()


def _load(symbol: str, period: str, interval: str) -> None:
    state = replay.session()
    with st.spinner(f"Loading {symbol}…"):
        loaded = context.attempt(context.prices, symbol, period, interval)
    if not loaded.ok:
        state.message = ("error", loaded.error)
        return
    replay.load(symbol, loaded.value, context.currency_of(symbol), interval, period)


def _trade(side: str, state: replay.Session) -> None:
    action = state.engine.buy if side == "buy" else state.engine.sell
    result = action(state.price, state.timestamp)
    state.message = ("success" if result["success"] else "warning", result["message"])


def _controls(state: replay.Session) -> None:
    slider, back, play, forward = st.columns([6, 1, 1, 1])
    with slider:
        # Sync the widget's stored value BEFORE it renders. A keyed widget's own
        # state wins over the value argument, so stepping or playing would be
        # undone by the stale slider on the very next rerun.
        if st.session_state.get("sim_slider") != state.index:
            st.session_state["sim_slider"] = state.index
        position = st.slider("Candle", 0, len(state.frame) - 1, key="sim_slider",
                             label_visibility="collapsed")
        if position != state.index:
            state.index = position
            state.paused_event = None
    if back.button("⏮", width="stretch", help="Step back one candle"):
        replay.step(-1)
        st.rerun()
    if state.playing:
        if play.button("⏸", width="stretch", help="Pause — keeps the position and portfolio"):
            state.playing = False
            st.rerun()
    else:
        if play.button("▶", width="stretch", type="primary",
                       help="Play from the current candle"):
            state.playing = True
            state.paused_event = None
            st.rerun()
    if forward.button("⏭", width="stretch", help="Step forward one candle"):
        replay.step(1)
        st.rerun()


def _headline_metrics(state: replay.Session) -> None:
    snapshot = state.engine.snapshot(state.price)
    columns = st.columns(4)
    layout.metric(columns[0], "Portfolio", money(snapshot["portfolio_value"], state.currency, 0),
                  f"{snapshot['return_pct']:+.2f}%")
    layout.metric(columns[1], "P&L", signed_money(snapshot["total_pnl"], state.currency),
                  f"realised {signed_money(snapshot['realized_pnl'], state.currency)}",
                  delta_color="off", delta_arrow="off")
    layout.metric(columns[2], "Win rate", f"{snapshot['win_rate']:.0f}%",
                  f"{snapshot['closed_trades']} closed", delta_color="off", delta_arrow="off")
    position = ("flat" if state.engine.holdings == 0
                else f"{state.engine.holdings:+d} @ "
                     f"{money(state.engine.avg_entry_price, state.currency)}")
    layout.metric(columns[3], "Position", position,
                  f"cash {money(state.engine.balance, state.currency, 0)}",
                  delta_color="off", delta_arrow="off")


def _learning_panel(state: replay.Session) -> None:
    event = state.paused_event
    st.warning(f"**{event['label']}** at candle {state.index + 1} · "
               f"{money(event['price'], state.currency)}")
    st.plotly_chart(price_charts.event_chart(state.frame, event, currency=state.currency),
                    width="stretch", key="sim_event_chart")

    if not state.revealed:
        st.markdown("**What happens next?**")
        choice = st.radio("Your call", ["BUY", "SELL", "HOLD"], horizontal=True,
                          key="sim_call", label_visibility="collapsed")
        if st.button("Show outcome", type="primary", key="sim_reveal"):
            state.call = choice
            state.revealed = True
            st.rerun()
        return

    result = replay.outcome(state)
    correct = state.call == result["direction"]
    st.markdown(f"Over the next **{result['bars']} candles** price moved "
                f"**{signed_money(result['move'], state.currency, 2)}** "
                f"({result['percent']:+.2f}%), which favoured **{result['direction']}**.")
    if state.call:
        (st.success if correct else st.info)(
            f"You said {state.call}. " + ("Good call." if correct
                                          else f"The move favoured {result['direction']}."))
    if state.paused_event["kind"] == "signal":
        st.caption(f"The strategy's signal here was **{state.paused_event['signal']}**.")
    if st.button("Continue", type="primary", key="sim_continue"):
        # Step past the paused candle so the replay doesn't stop on it again.
        state.index = min(state.index + 1, len(state.frame) - 1)
        state.paused_event = None
        state.revealed = False
        state.playing = True
        st.rerun()


def _results(state: replay.Session) -> None:
    engine = state.engine
    if not engine.trades:
        st.caption("No trades yet. Trade manually, or pick a strategy and press play.")
        return

    st.subheader("Performance")
    stats = performance.summarise(engine.trades, engine.equity_curve, engine.initial_capital)
    columns = st.columns(5)
    layout.metric(columns[0], "Total return", f"{stats['total_return']:+.2f}%")
    layout.metric(columns[1], "Realised P&L", signed_money(stats["total_pnl"], state.currency))
    layout.metric(columns[2], "Max drawdown", f"{stats['max_drawdown']:.2f}%")
    layout.metric(columns[3], "Sharpe", f"{stats['sharpe_ratio']:.2f}")
    factor = stats["profit_factor"]
    layout.metric(columns[4], "Profit factor", "∞" if factor == float("inf") else f"{factor:.2f}")

    st.plotly_chart(portfolio_charts.equity_curve(engine.equity_curve,
                                                  engine.initial_capital, state.currency),
                    width="stretch", key="sim_equity")

    left, right = st.columns([3, 2])
    with left:
        st.caption("Trade log")
        st.dataframe(pd.DataFrame([
            {"Time": str(t.timestamp)[:16], "Action": t.action, "Qty": t.quantity,
             "Price": money(t.price, state.currency), "P&L": signed_money(t.pnl, state.currency),
             "Strategy": t.strategy} for t in reversed(engine.trades)]),
            hide_index=True, width="stretch", height=260, key="sim_trades")
    with right:
        st.caption("By strategy")
        st.dataframe(performance.by_strategy(engine.trades), hide_index=True,
                     width="stretch", key="sim_by_strategy")


def render() -> None:
    symbol = context.ticker()
    state = replay.session()

    # A handoff from the backtester: load its ticker and strategy straight away.
    request = st.session_state.pop(context.SIM_REQUEST_KEY, None)
    if request:
        loaded = context.attempt(context.prices, request["symbol"], request["period"], "1d")
        if loaded.ok:
            replay.load(request["symbol"], loaded.value,
                        context.currency_of(request["symbol"]), "1d", request["period"],
                        strategy_key=request["strategy"], params=request.get("params", {}))
        else:
            state.message = ("error", loaded.error)

    _sidebar(state, symbol)
    layout.page_header("Trading Simulator",
                       "Replay real market data candle by candle and paper trade it, "
                       "long or short. Nothing here places a real order.")

    if state.message:
        kind, text = state.message
        getattr(st, kind)(layout.markdown_safe(text))
        state.message = None

    if not state.loaded:
        st.info(f"Press **Load data** in the sidebar to replay {symbol}.")
        return

    st.markdown(f"### {state.symbol} · {label_for(state.strategy_key)}")
    st.caption(f"Candle {state.index + 1} of {len(state.frame)} · "
               f"{str(state.timestamp)[:10]} · close {money(state.price, state.currency)}")

    _headline_metrics(state)
    _controls(state)

    if state.playing:
        replay.tick()
    else:
        render_chart(state, key="static_chart")

    if state.paused_event:
        _learning_panel(state)

    _results(state)
