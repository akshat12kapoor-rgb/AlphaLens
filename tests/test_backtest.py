"""
The backtest engine.

Includes golden numbers from the original AlgoBacktester CLI: the restructure
must not change what a backtest reports.
"""
import pytest

from alphalens.backtest import engine, sweep
from alphalens.signals.strategies import Context, get


def test_sample_sma_crossover_matches_the_original_tool(sample):
    """SMA 20/50 on the bundled sample data, as the old CLI reported it:
    +6.12%, Sharpe 0.30, 8 trades, $10,611.57 from $10,000."""
    result = engine.run_strategy(sample, get("ma_crossover"), symbol="SAMPLE",
                                 capital=10_000)
    assert result.final_equity == pytest.approx(10_611.57, abs=0.01)
    assert result.total_return == pytest.approx(0.0612, abs=0.0001)
    assert result.sharpe == pytest.approx(0.30, abs=0.005)
    assert result.max_drawdown == pytest.approx(-0.1049, abs=0.0001)
    assert result.exposure == pytest.approx(0.6165, abs=0.0001)
    assert result.trades == 8


def test_sample_buy_and_hold_matches_the_original_benchmark(sample):
    benchmark = engine.run_strategy(sample, get("buy_and_hold"), symbol="SAMPLE",
                                    capital=10_000)
    assert benchmark.total_return == pytest.approx(0.2031, abs=0.0001)
    assert benchmark.sharpe == pytest.approx(0.64, abs=0.005)


def test_a_position_is_held_over_the_next_bar_not_the_current_one(sample):
    """The engine must trade bar i's decision at bar i+1's return. If it used
    the same bar, a strategy that is long only on up-bars would never lose."""
    closes = sample["close"].tolist()
    cheating = [1.0 if i > 0 and closes[i] > closes[i - 1] else 0.0
                for i in range(len(closes))]
    result = engine.run(sample, cheating, strategy="hindsight", symbol="SAMPLE")
    # With the correct lag this is an ordinary, losing-ish strategy, not a rocket.
    assert result.total_return < 5.0


def test_commission_reduces_return_when_the_strategy_trades(sample):
    free = engine.run_strategy(sample, get("ma_crossover"), symbol="SAMPLE", commission=0.0)
    costly = engine.run_strategy(sample, get("ma_crossover"), symbol="SAMPLE", commission=0.01)
    assert costly.total_return < free.total_return
    assert free.trades == costly.trades


def test_slippage_reduces_return_like_commission_does(sample):
    free = engine.run_strategy(sample, get("ma_crossover"), symbol="SAMPLE", slippage=0.0)
    costly = engine.run_strategy(sample, get("ma_crossover"), symbol="SAMPLE", slippage=0.01)
    assert costly.total_return < free.total_return
    assert free.trades == costly.trades


def test_final_bar_position_change_is_costed_separately_from_equity(sample):
    """A position that only opens on the very last bar has no future bar to
    realize a return over, but opening it is still a real cost."""
    positions = [0.0] * (len(sample) - 1) + [1.0]
    result = engine.run(sample, positions, strategy="last-bar-entry", symbol="SAMPLE",
                        commission=0.01, slippage=0.0)
    assert result.final_position == 1.0
    assert result.unrealized_entry_cost == pytest.approx(0.01 * result.equity[-1])
    # It must not leak into the realized series - nothing to realize it against.
    assert result.trades == 0
    assert result.total_return == 0.0


def test_unrealized_entry_cost_is_zero_when_the_final_position_is_unchanged(sample):
    result = engine.run(sample, [1.0] * len(sample), strategy="always-long", symbol="SAMPLE")
    assert result.unrealized_entry_cost == 0.0
    assert result.final_position == 1.0


def test_buy_and_hold_with_no_costs_is_the_price_return(sample):
    result = engine.run_strategy(sample, get("buy_and_hold"), symbol="SAMPLE", commission=0.0)
    price_return = sample["close"].iloc[-1] / sample["close"].iloc[0] - 1
    assert result.total_return == pytest.approx(price_return, rel=1e-9)


def test_flat_strategy_never_moves_equity(sample):
    result = engine.run(sample, [0.0] * len(sample), strategy="flat", symbol="SAMPLE")
    assert result.total_return == 0.0
    assert result.trades == 0
    assert result.exposure == 0.0
    assert result.max_drawdown == 0.0


def test_short_positions_profit_when_prices_fall(sample):
    falling = sample.iloc[::-1].copy()
    falling.index = sample.index
    rising_return = engine.run(falling, [1.0] * len(falling), strategy="long",
                               symbol="X", commission=0.0).total_return
    short_return = engine.run(falling, [-1.0] * len(falling), strategy="short",
                              symbol="X", commission=0.0).total_return
    assert rising_return < 0 < short_return


def test_mismatched_position_count_is_rejected(sample):
    with pytest.raises(ValueError, match="positions"):
        engine.run(sample, [1.0] * 3, strategy="x", symbol="X")


def test_too_few_bars_is_rejected(sample):
    with pytest.raises(ValueError, match="at least 3 bars"):
        engine.run(sample.iloc[:2], [1.0, 1.0], strategy="x", symbol="X")


def test_drawdown_series_is_never_positive(sample):
    result = engine.run_strategy(sample, get("ma_crossover"), symbol="SAMPLE")
    assert result.drawdown_series.max() <= 1e-12


def test_result_label_records_the_settings_used(sample):
    result = engine.run_strategy(sample, get("ma_crossover"), symbol="SAMPLE",
                                 allow_short=True, fast=10, slow=40)
    assert "10" in result.strategy and "40" in result.strategy
    assert "long/short" in result.strategy


def test_sweep_covers_the_grid_and_skips_invalid_pairs(sample):
    context = Context.for_frame(sample)
    grid = sweep.grid(sample, get("ma_crossover"),
                      {"fast": [10, 20, 50], "slow": [20, 50]}, context=context)
    assert len(grid) == 3  # 10/20, 10/50, 20/50; the rest are fast >= slow
    assert set(grid.columns) >= {"fast", "slow", "sharpe", "total_return", "trades"}
    assert sweep.best(grid)["sharpe"] == grid["sharpe"].max()


def test_sweep_of_an_empty_grid_is_empty(sample):
    grid = sweep.grid(sample, get("ma_crossover"), {"fast": [50], "slow": [50]})
    assert grid.empty
    assert sweep.best(grid) is None
