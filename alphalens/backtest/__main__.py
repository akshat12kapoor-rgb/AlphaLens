"""
Command line for the backtester.

    python -m alphalens.backtest                            # SMA 20/50 on the sample data
    python -m alphalens.backtest --strategy rsi --short
    python -m alphalens.backtest --symbol AAPL --period 5y  # live Yahoo prices
    python -m alphalens.backtest prices.csv --fast 10 --slow 100
"""
from __future__ import annotations

import argparse
import sys

from alphalens.backtest import engine
from alphalens.core.config import DEFAULT_COMMISSION, INITIAL_CAPITAL
from alphalens.core.currency import money
from alphalens.data import csv_prices
from alphalens.data.models import DataUnavailable
from alphalens.signals import strategies


def summarise(result: engine.BacktestResult, benchmark: engine.BacktestResult) -> str:
    rows = [
        ("Strategy", result.strategy),
        ("Symbol", result.symbol),
        ("Period", f"{result.dates[0].date()} -> {result.dates[-1].date()} "
                   f"({len(result.dates)} bars)"),
        ("Initial capital", money(result.initial_capital, result.currency)),
        ("Final equity", money(result.final_equity, result.currency)),
        ("Total return", f"{result.total_return:+.2%}"),
        ("CAGR", f"{result.cagr:+.2%}"),
        ("Volatility (ann.)", f"{result.volatility:.2%}"),
        ("Sharpe", f"{result.sharpe:.2f}"),
        ("Max drawdown", f"{result.max_drawdown:.2%}"),
        ("Win rate", f"{result.win_rate:.2%}"),
        ("Exposure", f"{result.exposure:.2%}"),
        ("Trades", str(result.trades)),
    ]
    width = max(len(label) for label, _ in rows)
    body = "\n".join(f"{label:<{width}}  {value}" for label, value in rows)
    return (f"{body}\n\nBenchmark (buy & hold): {benchmark.total_return:+.2%} | "
            f"Sharpe {benchmark.sharpe:.2f} | MaxDD {benchmark.max_drawdown:.2%}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m alphalens.backtest",
        description="Backtest a strategy against historical prices.")
    parser.add_argument("csv", nargs="?", help="OHLCV CSV (default: the sample data)")
    parser.add_argument("--symbol", help="fetch this symbol from Yahoo instead of a CSV")
    parser.add_argument("--period", default="2y", help="history to fetch (default 2y)")
    parser.add_argument("--strategy", default="ma_crossover",
                        choices=list(strategies.STRATEGIES), help="strategy key")
    parser.add_argument("--fast", type=int, help="fast SMA window (MA crossover)")
    parser.add_argument("--slow", type=int, help="slow SMA window (MA crossover)")
    parser.add_argument("--short", action="store_true", help="allow short positions")
    parser.add_argument("--capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION,
                        help="cost per unit of turnover (default 0.0005)")
    args = parser.parse_args(argv)

    currency = "USD"
    try:
        if args.symbol:
            from alphalens.data import yahoo
            frame = yahoo.prices(args.symbol, period=args.period, interval="1d")
            symbol = args.symbol.upper()
            currency = yahoo.quote(args.symbol).currency
        elif args.csv:
            frame, symbol = csv_prices.load_prices(args.csv)
        else:
            frame, symbol = csv_prices.sample_prices()
    except DataUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    params = {k: v for k, v in (("fast", args.fast), ("slow", args.slow)) if v is not None}
    strategy = strategies.get(args.strategy)
    try:
        result = engine.run_strategy(frame, strategy, symbol=symbol, currency=currency,
                                     allow_short=args.short, capital=args.capital,
                                     commission=args.commission, **params)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    benchmark = engine.run_strategy(frame, strategies.get(strategies.BENCHMARK),
                                    symbol=symbol, currency=currency,
                                    capital=args.capital, commission=args.commission)
    print(summarise(result, benchmark))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
