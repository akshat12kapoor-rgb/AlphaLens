"""
The replay loop and its session state.

The ticking fragment lives here, at module level, because `st.fragment` keys off
the function's identity: defined inside the page script it would be rebuilt on
every rerun. It reads everything from session state and captures nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st

from alphalens.core.config import INITIAL_CAPITAL
from alphalens.signals import indicators
from alphalens.signals.strategies import Context, Strategy, get
from alphalens.trading.engine import PaperTradingEngine

STATE = "simulator"
#: Seconds per candle while playing. Fast enough to watch, slow enough that
#: Pause registers within a quarter second.
TICK = 0.25
#: Candles shown after the current one when Learning Mode reveals an outcome.
OUTCOME_BARS = 5
#: Bars kept on screen in the replay chart. Without this, `visible` grows for
#: the whole session - the candlestick, every indicator overlay and the
#: chart's serialized payload to the browser all get redrawn bigger on every
#: tick, so a long playback gets slower as it goes rather than staying flat.
#: Full history stays in `frame`/`engine` for P&L accounting either way.
CHART_WINDOW = 250


@dataclass
class Session:
    """Everything one replay needs. Held in session state under STATE."""

    symbol: str = ""
    currency: str = "USD"
    interval: str = "1d"
    period: str = "1y"
    frame: pd.DataFrame | None = None
    context: Context | None = None
    signals: pd.Series | None = None
    strategy_key: str = "manual"
    params: dict = field(default_factory=dict)
    engine: PaperTradingEngine = field(default_factory=PaperTradingEngine)
    index: int = 0
    playing: bool = False
    learning: bool = False
    paused_event: dict | None = None
    revealed: bool = False
    call: str | None = None
    message: tuple[str, str] | None = None
    last_action: tuple[str, int] | None = None

    @property
    def loaded(self) -> bool:
        return self.frame is not None and not self.frame.empty

    @property
    def price(self) -> float:
        return float(self.frame["close"].iloc[self.index])

    @property
    def timestamp(self):
        return self.frame.index[self.index]

    @property
    def visible_start(self) -> int:
        """First bar included in `visible` - the window's left edge."""
        return max(0, self.index + 1 - CHART_WINDOW)

    @property
    def visible(self) -> pd.DataFrame:
        return self.frame.iloc[self.visible_start:self.index + 1]

    def signal_at(self, index: int) -> str:
        if self.signals is None:
            return "HOLD"
        return str(self.signals.iloc[index])


def session() -> Session:
    if STATE not in st.session_state:
        st.session_state[STATE] = Session()
    return st.session_state[STATE]


def load(symbol: str, frame: pd.DataFrame, currency: str, interval: str, period: str,
         strategy_key: str | None = None, params: dict | None = None) -> Session:
    """Prepare a replay: indicators, detections, signals, a fresh account."""
    state = session()
    enriched = indicators.enrich(frame)
    context = Context.for_frame(enriched)
    state.symbol = symbol
    state.currency = currency
    state.interval, state.period = interval, period
    state.frame, state.context = enriched, context
    if strategy_key:
        state.strategy_key = strategy_key
    if params is not None:
        state.params = params
    state.signals = signals_for(state)
    state.engine = PaperTradingEngine(INITIAL_CAPITAL, currency)
    # Start part-way in so the moving averages and RSI mean something on screen.
    state.index = min(50, len(enriched) - 1)
    state.playing = False
    state.paused_event = None
    state.revealed = False
    state.call = None
    state.last_action = None
    state.message = ("success", f"Loaded {len(enriched)} candles for {symbol} · "
                                f"{len(context.fvg)} FVGs · {len(context.sweeps)} sweeps")
    return state


def signals_for(state: Session) -> pd.Series | None:
    """The chosen strategy's signals, or None under manual trading."""
    if state.strategy_key == "manual" or state.frame is None:
        return None
    return get(state.strategy_key).signals(state.frame, state.context, **state.params)


def set_strategy(key: str, params: dict | None = None) -> None:
    state = session()
    state.strategy_key = key
    state.params = params or {}
    if state.loaded:
        state.signals = signals_for(state)


def step(delta: int) -> None:
    """Move the replay by `delta` candles.

    Stepping forward must trade exactly like ticking does, one bar at a time —
    otherwise a strategy's signals are only honoured when the user presses
    Play, and the same replay produces different fills depending on which
    control moved it.
    """
    state = session()
    if not state.loaded:
        return
    target = max(0, min(state.index + delta, len(state.frame) - 1))
    if delta > 0:
        while state.index < target:
            _auto_trade(state)
            state.engine.record_value(state.timestamp, state.price)
            state.index += 1
    else:
        state.index = target
    state.paused_event = None
    state.revealed = False
    state.call = None


def reset_account() -> None:
    state = session()
    state.engine = PaperTradingEngine(INITIAL_CAPITAL, state.currency)
    state.playing = False
    state.message = ("info", "Portfolio reset to its starting capital.")


# ── the ticking fragment ────────────────────────────────────────────────────

@st.fragment(run_every=TICK)
def tick() -> None:
    """Advance one candle per tick while playing.

    Only this fragment redraws while a replay runs, which is what keeps the page
    from flickering and the scroll position from jumping. Anything that has to
    change the rest of the page (finishing, or pausing for Learning Mode) exits
    with a full rerun.
    """
    state = st.session_state.get(STATE)
    if state is None or not state.playing or not state.loaded:
        return

    if state.index >= len(state.frame) - 1:
        state.playing = False
        state.message = ("success", "Replay complete — review the performance below.")
        st.rerun(scope="app")

    # The trade for this bar must execute before we check whether Learning Mode
    # wants to pause on it — otherwise a pause-worthy signal is the one signal
    # that never gets traded, because the rerun below unwinds before it fires.
    _auto_trade(state)

    event = _pause_event(state)
    if event is not None:
        state.playing = False
        state.paused_event = event
        state.revealed = False
        state.call = None
        st.rerun(scope="app")

    state.engine.record_value(state.timestamp, state.price)
    state.index += 1

    from alphalens.ui.pages import simulator as page

    page.render_chart(state, key="replay_chart")


def _auto_trade(state: Session) -> None:
    """Execute the current bar's signal, if a strategy is driving."""
    if state.strategy_key == "manual":
        return
    signal = state.signal_at(state.index)
    if signal in ("BUY", "SELL"):
        result = state.engine.execute(signal, state.price, state.timestamp,
                                      get(state.strategy_key).name)
        if result and result.get("success"):
            state.last_action = (result["message"], state.index)


def windowed_gaps(gaps: pd.DataFrame | None, offset: int) -> pd.DataFrame | None:
    """Rebase FVG rows onto a windowed frame that starts `offset` bars in.

    `start_idx` is a position in the full frame; the chart looks it up
    positionally in whatever frame it's given, so a gap that starts before the
    window isn't drawable in it at all - there's no candle left to anchor it
    to.
    """
    if not offset or gaps is None or gaps.empty:
        return gaps
    visible = gaps[gaps["start_idx"] >= offset].copy()
    visible["start_idx"] = visible["start_idx"] - offset
    return visible


def _pause_event(state: Session) -> dict | None:
    """What Learning Mode should stop on at this candle, if anything."""
    if not state.learning:
        return None
    index = state.index

    signal = state.signal_at(index)
    if signal in ("BUY", "SELL"):
        return {"kind": "signal", "label": signal, "index": index,
                "price": state.price, "signal": signal}

    gaps = state.context.fvg if state.context else None
    if gaps is not None and not gaps.empty:
        # A gap completes one bar after its middle candle.
        match = gaps[gaps["start_idx"] == index - 1]
        if not match.empty:
            row = match.iloc[0]
            return {"kind": "fvg", "label": f"{row['type']} FVG", "index": index,
                    "price": state.price, "direction": row["type"],
                    "top": row["top"], "bottom": row["bottom"]}

    sweeps = state.context.sweeps if state.context else None
    if sweeps is not None and not sweeps.empty:
        match = sweeps[sweeps["index"] == state.timestamp]
        if not match.empty:
            row = match.iloc[0]
            return {"kind": "sweep", "label": f"{row['type'].replace('_', ' ')} sweep",
                    "index": index, "price": state.price,
                    "swept_level": row["swept_level"]}
    return None


def outcome(state: Session) -> dict[str, Any]:
    """What happened over the next few candles, for Learning Mode's reveal."""
    start = state.index
    end = min(start + OUTCOME_BARS, len(state.frame) - 1)
    move = float(state.frame["close"].iloc[end]) - float(state.frame["close"].iloc[start])
    percent = move / float(state.frame["close"].iloc[start]) * 100
    return {"bars": end - start, "move": move, "percent": percent,
            "direction": "BUY" if percent > 0.2 else "SELL" if percent < -0.2 else "HOLD"}
