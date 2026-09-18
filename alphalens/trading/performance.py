"""Statistics over a paper-trading session's trade log and equity curve."""
from __future__ import annotations

import numpy as np
import pandas as pd

from alphalens.core.config import INITIAL_CAPITAL, TRADING_DAYS
from alphalens.trading.engine import CLOSING_ACTIONS, Trade

EMPTY = dict(total_return=0.0, total_pnl=0.0, num_trades=0, num_wins=0, num_losses=0,
             win_rate=0.0, avg_win=0.0, avg_loss=0.0, profit_factor=0.0,
             max_drawdown=0.0, sharpe_ratio=0.0, calmar_ratio=0.0,
             best_trade=0.0, worst_trade=0.0)


def summarise(trades: list[Trade], equity_curve: list[tuple[object, float]],
              initial_capital: float = INITIAL_CAPITAL) -> dict:
    """Trade statistics plus equity-curve risk measures.

    Only closing trades (SELL, COVER) carry P&L, so win rate and profit factor
    are measured over those; opening trades would otherwise count as losses.
    """
    if not trades:
        return dict(EMPTY)

    closed = [t for t in trades if t.action in CLOSING_ACTIONS]
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_wins = sum(t.pnl for t in wins)
    gross_losses = abs(sum(t.pnl for t in losses))

    stats = dict(
        total_pnl=sum(t.pnl for t in closed),
        num_trades=len(trades),
        num_wins=len(wins),
        num_losses=len(losses),
        win_rate=(len(wins) / len(closed) * 100) if closed else 0.0,
        avg_win=float(np.mean([t.pnl for t in wins])) if wins else 0.0,
        avg_loss=float(np.mean([t.pnl for t in losses])) if losses else 0.0,
        profit_factor=(gross_wins / gross_losses) if gross_losses > 0 else float("inf"),
        best_trade=max((t.pnl for t in closed), default=0.0),
        worst_trade=min((t.pnl for t in closed), default=0.0),
    )

    if equity_curve:
        values = pd.Series([value for _, value in equity_curve], dtype=float)
        total_return = (values.iloc[-1] - initial_capital) / initial_capital * 100
        drawdowns = (values.cummax() - values) / values.cummax() * 100
        max_drawdown = float(drawdowns.max())
        returns = values.pct_change().dropna()
        sharpe = (float(returns.mean() / returns.std() * np.sqrt(TRADING_DAYS))
                  if len(returns) > 1 and returns.std() > 0 else 0.0)
        stats.update(total_return=total_return, max_drawdown=max_drawdown,
                     sharpe_ratio=sharpe,
                     calmar_ratio=(total_return / max_drawdown) if max_drawdown > 0 else 0.0)
    else:
        stats.update(total_return=stats["total_pnl"] / initial_capital * 100,
                     max_drawdown=0.0, sharpe_ratio=0.0, calmar_ratio=0.0)
    return stats


def by_strategy(trades: list[Trade]) -> pd.DataFrame:
    """Closed-trade P&L grouped by the strategy that placed it."""
    rows = [{"Strategy": t.strategy, "P&L": t.pnl, "Win": t.pnl > 0}
            for t in trades if t.action in CLOSING_ACTIONS]
    if not rows:
        return pd.DataFrame(columns=["Strategy", "Trades", "Total P&L", "Win Rate %"])

    summary = (pd.DataFrame(rows).groupby("Strategy")
               .agg(Trades=("P&L", "count"), total_pnl=("P&L", "sum"), win_rate=("Win", "mean"))
               .rename(columns={"total_pnl": "Total P&L", "win_rate": "Win Rate %"})
               .reset_index())
    summary["Win Rate %"] = (summary["Win Rate %"] * 100).round(1)
    summary["Total P&L"] = summary["Total P&L"].round(2)
    return summary
