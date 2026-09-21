"""Parameter sweeps: the same strategy over a grid of settings."""
from __future__ import annotations

import itertools

import pandas as pd

from alphalens.backtest import engine
from alphalens.core.config import DEFAULT_COMMISSION
from alphalens.signals.strategies import Context, Strategy

WARNING = (
    "Every cell is measured on this history, so the best one is the most fitted "
    "to it, not a forecast. Check a promising setting on another period or "
    "instrument before trusting it."
)


def grid(frame: pd.DataFrame, strategy: Strategy, params: dict[str, list[int]], *,
         symbol: str = "", allow_short: bool = False,
         commission: float = DEFAULT_COMMISSION, slippage: float = 0.0,
         context: Context | None = None) -> pd.DataFrame:
    """Run `strategy` over the cartesian product of `params`.

    Combinations the strategy rejects (a fast window at or above the slow one,
    say) are skipped rather than reported as failures.
    """
    context = context or Context.for_frame(frame)
    keys = list(params)
    rows = []
    for values in itertools.product(*(params[key] for key in keys)):
        setting = dict(zip(keys, values))
        try:
            result = engine.run_strategy(frame, strategy, symbol=symbol,
                                         allow_short=allow_short, commission=commission,
                                         slippage=slippage, context=context, **setting)
        except ValueError:
            continue
        rows.append({**setting, "sharpe": result.sharpe,
                     "total_return": result.total_return,
                     "max_drawdown": result.max_drawdown, "trades": result.trades})
    return pd.DataFrame(rows)


def best(results: pd.DataFrame, by: str = "sharpe") -> pd.Series | None:
    if results.empty:
        return None
    return results.loc[results[by].idxmax()]
