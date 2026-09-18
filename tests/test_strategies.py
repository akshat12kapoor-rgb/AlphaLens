"""
The strategy catalogue.

The important property here is that no strategy can see the future: the signal
for bar i must not change when later bars are added or removed. A backtest is
meaningless otherwise, and this is exactly what a refactor can quietly break.
"""
import pandas as pd
import pytest

from alphalens.signals import smc
from alphalens.signals.strategies import (BUY, HOLD, SELL, Context, STRATEGIES, TRADEABLE,
                                          events_from_positions, get, positions_from_events)


@pytest.mark.parametrize("key", TRADEABLE)
def test_every_strategy_produces_one_signal_per_bar(key, enriched, context):
    signals = get(key).signals(enriched, context)
    assert len(signals) == len(enriched)
    assert set(signals.unique()) <= {BUY, SELL, HOLD}


@pytest.mark.parametrize("key", TRADEABLE)
def test_every_strategy_produces_positions_within_bounds(key, enriched, context):
    positions = get(key).positions(enriched, context, allow_short=True)
    assert len(positions) == len(enriched)
    assert all(-1.0 <= p <= 1.0 for p in positions)


@pytest.mark.parametrize("key", TRADEABLE)
def test_no_strategy_looks_ahead(key, enriched, context):
    """Signals computed on a truncated history must match the full history.

    The last bar is excluded from the comparison: a Fair Value Gap is only
    knowable once its third candle closes, so the final bar of a truncated frame
    legitimately has no verdict yet.
    """
    cut = 300
    truncated = enriched.iloc[:cut]
    full = get(key).signals(enriched, context)
    partial = get(key).signals(truncated, Context.for_frame(truncated))
    assert list(partial[:cut - 1]) == list(full[:cut - 1])


def test_long_only_positions_never_go_short(enriched, context):
    positions = get("rsi").positions(enriched, context, allow_short=False)
    assert min(positions) == 0.0
    assert max(positions) == 1.0


def test_short_positions_appear_only_when_allowed(enriched, context):
    assert min(get("rsi").positions(enriched, context, allow_short=True)) == -1.0


def test_positions_carry_the_latest_event():
    signals = pd.Series([HOLD, BUY, HOLD, HOLD, SELL, HOLD])
    assert positions_from_events(signals) == [0.0, 1.0, 1.0, 1.0, 0.0, 0.0]
    assert positions_from_events(signals, allow_short=True) == [0.0, 1.0, 1.0, 1.0, -1.0, -1.0]


def test_events_fire_only_where_the_position_changes():
    assert list(events_from_positions([0.0, 1.0, 1.0, -1.0, -1.0, 0.0])) == [
        HOLD, BUY, HOLD, SELL, HOLD, BUY]


def test_the_two_forms_round_trip_for_an_always_in_market_series():
    """Events cannot distinguish "close the short" from "go long", so the round
    trip is exact only while the strategy is always in the market - which is how
    the auto-traded strategies run."""
    positions = [1.0, 1.0, -1.0, -1.0, 1.0]
    assert positions_from_events(events_from_positions(positions), allow_short=True) == positions


def test_returning_to_flat_reads_as_a_buy_when_converted_back():
    assert list(events_from_positions([-1.0, 0.0])) == [SELL, BUY]
    assert positions_from_events(events_from_positions([-1.0, 0.0]), allow_short=True) == [-1.0, 1.0]


def test_ma_crossover_rejects_a_fast_window_at_or_above_the_slow_one(enriched, context):
    with pytest.raises(ValueError, match="shorter"):
        get("ma_crossover").positions(enriched, context, fast=50, slow=50)


def test_ma_crossover_is_flat_until_both_averages_exist(enriched, context):
    positions = get("ma_crossover").positions(enriched, context, fast=10, slow=30)
    assert set(positions[:29]) == {0.0}


def test_rsi_thresholds_change_how_often_it_trades(enriched, context):
    wide = get("rsi").signals(enriched, context, oversold=5, overbought=95)
    narrow = get("rsi").signals(enriched, context, oversold=45, overbought=55)
    assert (narrow != HOLD).sum() > (wide != HOLD).sum()


def test_fvg_strategy_acts_one_bar_after_the_gap_completes(enriched, context):
    signals = get("fvg").signals(enriched, context)
    first = context.fvg.iloc[0]
    assert signals.iloc[int(first["start_idx"]) + 1] == (
        BUY if first["type"] == "bullish" else SELL)


def test_sweep_strategy_fades_the_stop_hunt(enriched, context):
    signals = get("sweep").signals(enriched, context)
    row = context.sweeps.iloc[0]
    position = list(enriched.index).index(row["index"])
    assert signals.iloc[position] == (SELL if row["type"] == "buy_side" else BUY)


def test_buy_and_hold_is_always_long(enriched, context):
    assert set(STRATEGIES["buy_and_hold"].positions(enriched, context)) == {1.0}


def test_strategies_can_be_found_by_display_name():
    from alphalens.signals.strategies import by_name

    assert by_name("MA Crossover").key == "ma_crossover"
    with pytest.raises(KeyError):
        by_name("Nonexistent")


def test_unknown_key_names_the_valid_ones():
    with pytest.raises(KeyError, match="choose from"):
        get("nope")
