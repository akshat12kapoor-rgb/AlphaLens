"""
The strategy catalogue, shared by the simulator and the backtester.

Previously each tool had its own idea of a strategy: the simulator emitted
BUY/SELL/HOLD events, the backtester wanted a target position per bar. Here a
strategy declares whichever form is natural for it and the other is derived, so
a backtest and a replay of the same strategy trade the same decisions:

- `signals(...)` -> per-bar "BUY" / "SELL" / "HOLD" events (what the simulator acts on)
- `positions(...)` -> per-bar target in [-1, 1] (what the backtest engine holds)

Every strategy decides bar *i* from bars up to and including *i*. The backtest
engine applies that position to the *i* -> *i*+1 return, so results contain no
look-ahead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from alphalens.signals import indicators, smc

BUY, SELL, HOLD = "BUY", "SELL", "HOLD"


@dataclass
class Context:
    """Pre-computed detections a strategy may need, so they are found once."""

    fvg: pd.DataFrame | None = None
    sweeps: pd.DataFrame | None = None

    @classmethod
    def for_frame(cls, frame: pd.DataFrame) -> "Context":
        fvg, sweeps = smc.analyse(frame)
        return cls(fvg=fvg, sweeps=sweeps)


@dataclass(frozen=True)
class Parameter:
    key: str
    label: str
    default: int
    minimum: int
    maximum: int
    help: str = ""


@dataclass(frozen=True)
class Strategy:
    """One tradeable idea, in whichever form it is naturally expressed."""

    key: str
    name: str
    summary: str
    explanation: str
    form: str  # "events" or "regime"
    build: Callable[..., pd.Series]
    parameters: tuple[Parameter, ...] = field(default_factory=tuple)

    def defaults(self) -> dict[str, int]:
        return {p.key: p.default for p in self.parameters}

    def signals(self, frame: pd.DataFrame, context: Context | None = None,
                **params) -> pd.Series:
        """Per-bar BUY / SELL / HOLD."""
        options = {**self.defaults(), **params}
        raw = self.build(indicators.ensure(frame), context or Context(), **options)
        if self.form == "events":
            return raw
        return events_from_positions(raw)

    def positions(self, frame: pd.DataFrame, context: Context | None = None,
                  allow_short: bool = False, **params) -> list[float]:
        """Per-bar target position: 1 long, 0 flat, -1 short."""
        options = {**self.defaults(), **params}
        raw = self.build(indicators.ensure(frame), context or Context(), **options)
        if self.form == "regime":
            exit_position = -1.0 if allow_short else 0.0
            return [1.0 if held > 0 else exit_position for held in raw]
        return positions_from_events(raw, allow_short)


# ── converting between the two forms ────────────────────────────────────────

def positions_from_events(signals: pd.Series, allow_short: bool = False) -> list[float]:
    """Hold the direction of the latest event - the simulator's auto-trader
    behaviour, minus its position sizing."""
    exit_position = -1.0 if allow_short else 0.0
    held, out = 0.0, []
    for signal in signals:
        if signal == BUY:
            held = 1.0
        elif signal == SELL:
            held = exit_position
        out.append(held)
    return out


def events_from_positions(positions) -> pd.Series:
    """Emit an event whenever the target position changes direction.

    Events carry less information than positions: "close the short" and "go
    long" are both a BUY, so a position series that returns to flat becomes long
    when converted back. Round-tripping is exact only for always-in-the-market
    series, which is how the auto-traded strategies actually run.
    """
    values = list(positions)
    out, previous = [], 0.0
    for held in values:
        if held > previous:
            out.append(BUY)
        elif held < previous:
            out.append(SELL)
        else:
            out.append(HOLD)
        previous = held
    index = positions.index if isinstance(positions, pd.Series) else None
    return pd.Series(out, index=index, dtype=str)


# ── the strategies ──────────────────────────────────────────────────────────

def _rsi_events(frame: pd.DataFrame, context: Context, oversold: int = 30,
                overbought: int = 70) -> pd.Series:
    signals = pd.Series(HOLD, index=frame.index, dtype=str)
    series = frame["rsi"]
    # Edge-triggered: the bar the level is crossed, not every bar beyond it.
    signals[(series < oversold) & (series.shift(1) >= oversold)] = BUY
    signals[(series > overbought) & (series.shift(1) <= overbought)] = SELL
    return signals


def _macd_events(frame: pd.DataFrame, context: Context) -> pd.Series:
    signals = pd.Series(HOLD, index=frame.index, dtype=str)
    line, signal_line = frame["macd"], frame["macd_signal"]
    signals[(line > signal_line) & (line.shift(1) <= signal_line.shift(1))] = BUY
    signals[(line < signal_line) & (line.shift(1) >= signal_line.shift(1))] = SELL
    return signals


def _ma_regime(frame: pd.DataFrame, context: Context, fast: int = 20,
               slow: int = 50) -> pd.Series:
    """Long while the fast SMA is above the slow one.

    The windows are computed here rather than read from the enriched frame, so a
    parameter sweep can try any pair. Both SMAs need `slow` bars before they mean
    anything, so the strategy stays flat until then.
    """
    if fast >= slow:
        raise ValueError(f"fast window ({fast}) must be shorter than slow ({slow})")
    close = frame["close"]
    fast_ma = close.rolling(fast).mean()
    slow_ma = close.rolling(slow).mean()
    held = (fast_ma > slow_ma).astype(float)
    held[slow_ma.isna() | fast_ma.isna()] = 0.0
    return held


def _fvg_events(frame: pd.DataFrame, context: Context) -> pd.Series:
    """Act one bar after a gap completes: at `start_idx + 1` the third candle of
    the pattern has closed, so the gap is knowable."""
    signals = pd.Series(HOLD, index=frame.index, dtype=str)
    gaps = context.fvg if context.fvg is not None else smc.fair_value_gaps(frame)
    last = len(frame) - 1
    for _, row in gaps.iterrows():
        trigger = int(row["start_idx"]) + 1
        if trigger <= last:
            signals.iloc[trigger] = BUY if row["type"] == "bullish" else SELL
    return signals


def _sweep_events(frame: pd.DataFrame, context: Context) -> pd.Series:
    """Fade the stop hunt: buy a sell-side sweep, sell a buy-side one."""
    signals = pd.Series(HOLD, index=frame.index, dtype=str)
    sweeps = context.sweeps if context.sweeps is not None else smc.liquidity_sweeps(frame)
    position_of = {timestamp: i for i, timestamp in enumerate(frame.index)}
    for _, row in sweeps.iterrows():
        i = position_of.get(row["index"])
        if i is not None:
            signals.iloc[i] = SELL if row["type"] == "buy_side" else BUY
    return signals


def _buy_and_hold(frame: pd.DataFrame, context: Context) -> pd.Series:
    return pd.Series(1.0, index=frame.index)


STRATEGIES: dict[str, Strategy] = {
    s.key: s for s in [
        Strategy(
            key="ma_crossover", name="MA Crossover", form="regime", build=_ma_regime,
            summary="Long while the fast SMA is above the slow SMA.",
            explanation=(
                "A trend-following classic. The fast average reacts to recent prices, "
                "the slow one to the longer trend; the fast crossing above (a *golden "
                "cross*) says momentum has turned up, and crossing below (a *death "
                "cross*) that it has turned down."),
            parameters=(
                Parameter("fast", "Fast SMA", 20, 2, 200, "Bars in the fast average."),
                Parameter("slow", "Slow SMA", 50, 3, 400, "Bars in the slow average."),
            ),
        ),
        Strategy(
            key="rsi", name="RSI", form="events", build=_rsi_events,
            summary="Buy when RSI crosses below oversold, sell when it crosses above overbought.",
            explanation=(
                "A mean-reversion idea. RSI measures how one-sided recent moves have "
                "been; below 30 the selling is considered stretched and above 70 the "
                "buying is. It trades the crossing, not the level, so it fires once per "
                "excursion instead of every bar."),
            parameters=(
                Parameter("oversold", "Oversold level", 30, 5, 45, "Buy when RSI crosses below."),
                Parameter("overbought", "Overbought level", 70, 55, 95, "Sell when RSI crosses above."),
            ),
        ),
        Strategy(
            key="macd", name="MACD", form="events", build=_macd_events,
            summary="Buy on the MACD line crossing above its signal line, sell on the cross below.",
            explanation=(
                "MACD is the gap between a fast and a slow exponential average, and its "
                "signal line is a smoothing of that gap. The crossings mark momentum "
                "changing direction, usually earlier than a moving-average crossover."),
        ),
        Strategy(
            key="fvg", name="Fair Value Gap", form="events", build=_fvg_events,
            summary="Buy after a bullish Fair Value Gap completes, sell after a bearish one.",
            explanation=(
                "A Fair Value Gap is a three-candle imbalance where price moved so "
                "quickly that the first and third candles do not overlap. The idea is "
                "that the gap marks genuine pressure, so the move continues."),
        ),
        Strategy(
            key="sweep", name="Liquidity Sweep", form="events", build=_sweep_events,
            summary="Buy after a sell-side stop hunt, sell after a buy-side one.",
            explanation=(
                "A sweep is a wick beyond a recent high or low that closes back inside "
                "the range: stops resting beyond the level were triggered and price "
                "rejected. Fading it bets the break was liquidity-driven, not a trend."),
        ),
        Strategy(
            key="buy_and_hold", name="Buy & Hold", form="regime", build=_buy_and_hold,
            summary="Fully invested from the first bar - the benchmark.",
            explanation="Own the instrument for the whole period. The bar every strategy has to clear.",
        ),
    ]
}

#: Strategies offered for trading, benchmark excluded.
TRADEABLE = [key for key in STRATEGIES if key != "buy_and_hold"]
BENCHMARK = "buy_and_hold"


def get(key: str) -> Strategy:
    try:
        return STRATEGIES[key]
    except KeyError:
        raise KeyError(f"unknown strategy {key!r}; choose from {list(STRATEGIES)}") from None


def by_name(name: str) -> Strategy:
    """Look a strategy up by its display name."""
    for strategy in STRATEGIES.values():
        if strategy.name == name:
            return strategy
    raise KeyError(f"no strategy named {name!r}")


def names(keys: list[str] | None = None) -> list[str]:
    return [STRATEGIES[key].name for key in (keys or list(STRATEGIES))]
