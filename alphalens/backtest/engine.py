"""
The backtest engine.

Convention: the position decided on bar i is held over the return from bar i to
bar i+1. That one-bar lag is what keeps a backtest honest - a signal computed
from today's close cannot be traded at today's close.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from alphalens.core.config import DEFAULT_COMMISSION, INITIAL_CAPITAL, TRADING_DAYS
from alphalens.signals.strategies import Context, Strategy


@dataclass
class BacktestResult:
    """What a strategy did over one price series."""

    strategy: str
    symbol: str
    currency: str
    dates: list = field(repr=False)
    equity: list[float] = field(repr=False)
    returns: list[float] = field(repr=False)
    positions: list[float] = field(repr=False)
    trades: int = 0
    initial_capital: float = INITIAL_CAPITAL

    @property
    def final_equity(self) -> float:
        return self.equity[-1] if self.equity else self.initial_capital

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_capital - 1.0

    @property
    def years(self) -> float:
        return max(len(self.returns) / TRADING_DAYS, 1e-9)

    @property
    def cagr(self) -> float:
        if self.final_equity <= 0:
            return -1.0
        return (self.final_equity / self.initial_capital) ** (1 / self.years) - 1.0

    @property
    def volatility(self) -> float:
        """Annualised standard deviation of returns."""
        return _stdev(self.returns) * math.sqrt(TRADING_DAYS)

    @property
    def sharpe(self) -> float:
        """Annualised Sharpe, risk-free rate assumed zero."""
        deviation = _stdev(self.returns)
        if deviation == 0:
            return 0.0
        return (_mean(self.returns) / deviation) * math.sqrt(TRADING_DAYS)

    @property
    def max_drawdown(self) -> float:
        """Largest peak-to-trough fall, as a negative fraction."""
        peak, worst = -math.inf, 0.0
        for value in self.equity:
            peak = max(peak, value)
            if peak > 0:
                worst = min(worst, value / peak - 1.0)
        return worst

    @property
    def win_rate(self) -> float:
        """Share of held bars that made money."""
        active = [r for r, p in zip(self.returns, self.positions) if p != 0]
        if not active:
            return 0.0
        return sum(1 for r in active if r > 0) / len(active)

    @property
    def exposure(self) -> float:
        """Share of bars with a position on."""
        if not self.positions:
            return 0.0
        return sum(1 for p in self.positions if p != 0) / len(self.positions)

    @property
    def drawdown_series(self) -> pd.Series:
        equity = pd.Series(self.equity, index=self.dates)
        return equity / equity.cummax() - 1.0

    def metrics(self) -> dict[str, float | int]:
        return {"Total return": self.total_return, "CAGR": self.cagr,
                "Volatility": self.volatility, "Sharpe": self.sharpe,
                "Max drawdown": self.max_drawdown, "Win rate": self.win_rate,
                "Exposure": self.exposure, "Trades": self.trades,
                "Final equity": self.final_equity}


def run(frame: pd.DataFrame, positions: list[float], *, strategy: str, symbol: str,
        currency: str = "USD", capital: float = INITIAL_CAPITAL,
        commission: float = DEFAULT_COMMISSION) -> BacktestResult:
    """Apply a position series to prices.

    `commission` is charged on the traded notional whenever the position changes,
    so a flat -> long switch of size 1.0 costs `commission` of equity.
    """
    if len(positions) != len(frame):
        raise ValueError(f"{len(positions)} positions for {len(frame)} bars")
    if len(frame) < 3:
        raise ValueError("a backtest needs at least 3 bars")

    closes = frame["close"].tolist()
    equity, returns, held = [capital], [], []
    trades, previous = 0, 0.0

    for i in range(len(frame) - 1):
        position = positions[i]
        turnover = abs(position - previous)
        if turnover > 0:
            trades += 1
        bar_return = closes[i + 1] / closes[i] - 1.0
        net = position * bar_return - turnover * commission
        equity.append(equity[-1] * (1 + net))
        returns.append(net)
        held.append(position)
        previous = position

    return BacktestResult(strategy=strategy, symbol=symbol, currency=currency,
                          dates=list(frame.index), equity=equity, returns=returns,
                          positions=held, trades=trades, initial_capital=capital)


def run_strategy(frame: pd.DataFrame, strategy: Strategy, *, symbol: str,
                 currency: str = "USD", allow_short: bool = False,
                 capital: float = INITIAL_CAPITAL, commission: float = DEFAULT_COMMISSION,
                 context: Context | None = None, **params) -> BacktestResult:
    """Backtest a catalogue strategy, naming it as the user chose it."""
    context = context or Context.for_frame(frame)
    positions = strategy.positions(frame, context, allow_short=allow_short, **params)
    label = strategy.name
    if params:
        label += " (" + ", ".join(f"{k} {v}" for k, v in params.items()) + ")"
    if allow_short:
        label += " long/short"
    return run(frame, positions, strategy=label, symbol=symbol, currency=currency,
               capital=capital, commission=commission)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    """Sample standard deviation."""
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((v - average) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)
