"""
Backtest any AlphaOS strategy with the AlgoBacktester engine.

The simulator's strategies emit BUY / SELL / HOLD events; the backtester wants
a target position per bar. SignalStrategy bridges them by holding the direction
of the most recent signal - the same "always in the market" behaviour the
simulator's auto-trader has, minus its position sizing. None of the simulator's
signals look ahead (RSI/MACD/MA use the current and previous bar, sweeps compare
against the prior 20 bars, an FVG only fires once its third candle has closed),
and the engine trades a bar-i position over the i -> i+1 return, so results are
free of look-ahead.

No Streamlit here: pages and tests both call these functions.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from shell import surfaces

surfaces.use_backtester()
from backtester import BacktestResult, run_backtest  # noqa: E402
from data_loader import Bar, PriceSeries, load_csv  # noqa: E402
from strategies.base import BuyAndHold, Strategy  # noqa: E402
from strategies.moving_average import MovingAverageCrossover  # noqa: E402

SMA_CROSSOVER = "SMA Crossover"
SIGNAL_STRATEGIES = ["RSI Strategy", "MACD Strategy", "MA Crossover",
                     "FVG Strategy", "Liquidity Sweep"]
CATALOGUE = [SMA_CROSSOVER, *SIGNAL_STRATEGIES]
SAMPLE_CSV = surfaces.BACKTESTER_DIR / "data" / "SAMPLE.csv"

DESCRIPTIONS = {
    SMA_CROSSOVER: "Long while the fast SMA is above the slow SMA; flat (or short) otherwise.",
    "RSI Strategy": "Buy when RSI(14) crosses below 30, sell when it crosses above 70.",
    "MACD Strategy": "Buy when MACD(12,26,9) crosses above its signal line, sell on the cross below.",
    "MA Crossover": "Buy on the SMA 20/50 golden cross, sell on the death cross.",
    "FVG Strategy": "Buy after a bullish Fair Value Gap completes, sell after a bearish one.",
    "Liquidity Sweep": "Buy after a sell-side stop hunt below the prior 20-bar low, sell after a buy-side one.",
}


def series_from_frame(df: pd.DataFrame, symbol: str) -> PriceSeries:
    """Lowercase-OHLCV DataFrame -> PriceSeries. Daily bars only: the engine
    annualises with 252 bars per year."""
    dates = [ts.date() for ts in df.index]
    if len(set(dates)) != len(dates):
        raise ValueError("backtests need daily bars; this data has several bars per day")
    bars = [
        Bar(date=d, open=float(r.open), high=float(r.high), low=float(r.low),
            close=float(r.close), volume=int(r.volume))
        for d, r in zip(dates, df.itertuples())
    ]
    return PriceSeries(symbol, bars)


def frame_from_series(series: PriceSeries) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": [b.open for b in series], "high": [b.high for b in series],
         "low": [b.low for b in series], "close": [b.close for b in series],
         "volume": [b.volume for b in series]},
        index=pd.to_datetime([b.date for b in series]),
    )


def load_sample() -> PriceSeries:
    return load_csv(SAMPLE_CSV)


def load_upload(path, name: str) -> PriceSeries:
    series = load_csv(path, symbol=name.rsplit(".", 1)[0].upper())
    return series


class SignalStrategy(Strategy):
    """Hold the direction of the latest BUY/SELL event."""

    def __init__(self, name: str, signals: list[str], allow_short: bool):
        self.name = name + (" (long/short)" if allow_short else "")
        self.signals = signals
        self.allow_short = allow_short

    def generate_positions(self, series: PriceSeries) -> list[float]:
        if len(self.signals) != len(series):
            raise ValueError(f"{len(self.signals)} signals for {len(series)} bars")
        exit_position = -1.0 if self.allow_short else 0.0
        position, positions = 0.0, []
        for signal in self.signals:
            if signal == "BUY":
                position = 1.0
            elif signal == "SELL":
                position = exit_position
            positions.append(position)
        return positions


def simulator_signals(df: pd.DataFrame, strategy: str) -> list[str]:
    """The exact signals the Trading Simulator would generate for this data."""
    indicators = surfaces.module(surfaces.SIMULATOR, "indicators")
    smc = surfaces.module(surfaces.SIMULATOR, "smc_detector")
    strategies = surfaces.module(surfaces.SIMULATOR, "strategies")
    enriched = indicators.calculate_all_indicators(df)
    fvg, sweeps = smc.get_smc_analysis(enriched)
    return list(strategies.get_signals(enriched, strategy, fvg_df=fvg, sweeps_df=sweeps))


def build_strategy(name: str, series: PriceSeries, allow_short: bool,
                   fast: int = 20, slow: int = 50) -> Strategy:
    if name == SMA_CROSSOVER:
        strategy = MovingAverageCrossover(fast, slow, allow_short=allow_short)
        strategy.name = f"SMA {fast}/{slow} Crossover" + (" (long/short)" if allow_short else "")
        return strategy
    if name in SIGNAL_STRATEGIES:
        return SignalStrategy(name, simulator_signals(frame_from_series(series), name), allow_short)
    raise ValueError(f"unknown strategy {name!r}")


@dataclass
class LabRun:
    result: BacktestResult
    benchmark: BacktestResult
    positions: list[float]


def run(series: PriceSeries, name: str, *, allow_short: bool = False,
        capital: float = 100_000.0, commission: float = 0.0005,
        fast: int = 20, slow: int = 50) -> LabRun:
    if len(series) < 3:
        raise ValueError("need at least 3 bars to backtest")
    strategy = build_strategy(name, series, allow_short, fast, slow)
    positions = strategy.generate_positions(series)
    return LabRun(
        result=run_backtest(series, strategy, capital, commission),
        benchmark=run_backtest(series, BuyAndHold(), capital, commission),
        positions=positions,
    )


def sweep(series: PriceSeries, fasts: list[int], slows: list[int], *,
          allow_short: bool = False, commission: float = 0.0005) -> pd.DataFrame:
    """SMA crossover over a fast x slow grid. In-sample: the best cell is the
    most overfit one, not a forecast."""
    rows = []
    for fast in fasts:
        for slow in slows:
            if fast >= slow:
                continue
            r = run_backtest(series, MovingAverageCrossover(fast, slow, allow_short),
                             100_000.0, commission)
            rows.append({"fast": fast, "slow": slow, "sharpe": r.sharpe,
                         "total_return": r.total_return, "max_drawdown": r.max_drawdown,
                         "trades": r.trades})
    return pd.DataFrame(rows)


def simulator_equivalent(name: str, fast: int, slow: int) -> str | None:
    """The simulator strategy that trades the same idea, if there is one."""
    if name in SIGNAL_STRATEGIES:
        return name
    if name == SMA_CROSSOVER and (fast, slow) == (20, 50):
        return "MA Crossover"
    return None


def metrics(r: BacktestResult) -> dict[str, float | int]:
    return {"Total return": r.total_return, "CAGR": r.cagr, "Volatility": r.volatility,
            "Sharpe": r.sharpe, "Max drawdown": r.max_drawdown, "Win rate": r.win_rate,
            "Exposure": r.exposure, "Trades": r.trades, "Final equity": r.final_equity}
