"""The paper-trading engine: one signed holding, flips recorded as two trades."""
import pandas as pd
import pytest

from alphalens.trading import performance
from alphalens.trading.engine import PaperTradingEngine

NOW = pd.Timestamp("2024-01-01")


@pytest.fixture
def account():
    return PaperTradingEngine(initial_capital=10_000, currency="USD")


def test_buy_opens_a_long_and_spends_cash(account):
    account.buy(100.0, NOW, quantity=10)
    assert account.holdings == 10
    assert account.balance == 9_000
    assert account.avg_entry_price == 100.0


def test_default_size_is_a_fraction_of_cash(account):
    account.buy(100.0, NOW)
    assert account.holdings == 10  # 10% of 10,000 at 100


def test_a_buy_cannot_exceed_available_cash(account):
    account.buy(100.0, NOW, quantity=1_000)
    assert account.holdings == 100
    assert account.balance == 0


def test_selling_a_long_realises_the_gain(account):
    account.buy(100.0, NOW, quantity=10)
    account.sell(120.0, NOW, quantity=10)
    assert account.holdings == 0
    assert account.realized_pnl == pytest.approx(200.0)


def test_selling_past_flat_opens_a_short(account):
    account.buy(100.0, NOW, quantity=10)
    account.sell(120.0, NOW, quantity=10)
    account.sell(120.0, NOW, quantity=5)
    assert account.holdings == -5
    assert account.avg_entry_price == 120.0


def test_a_flip_is_recorded_as_two_trades(account):
    account.buy(100.0, NOW, quantity=10)
    result = account.sell(120.0, NOW, quantity=20)
    assert result["actions"] == ["SELL", "SHORT"]
    assert [t.action for t in account.trades] == ["BUY", "SELL", "SHORT"]


def test_covering_a_short_profits_when_the_price_fell(account):
    account.sell(100.0, NOW, quantity=10)
    account.buy(80.0, NOW, quantity=10)
    assert account.holdings == 0
    assert account.realized_pnl == pytest.approx(200.0)


def test_pnl_uses_one_formula_for_both_directions(account):
    account.buy(100.0, NOW, quantity=10)
    long_unrealised = account.unrealized_pnl(110.0)
    account.sell(110.0, NOW, quantity=10)
    account.sell(110.0, NOW, quantity=10)
    short_unrealised = account.unrealized_pnl(100.0)
    assert long_unrealised == pytest.approx(100.0)
    assert short_unrealised == pytest.approx(100.0)


def test_average_entry_price_blends_additions(account):
    account.buy(100.0, NOW, quantity=10)
    account.buy(120.0, NOW, quantity=10)
    assert account.avg_entry_price == pytest.approx(110.0)


def test_portfolio_value_marks_a_short_to_market(account):
    account.sell(100.0, NOW, quantity=10)
    assert account.portfolio_value(100.0) == pytest.approx(10_000)
    assert account.portfolio_value(90.0) == pytest.approx(10_100)


def test_execute_flips_between_sides(account):
    account.execute("BUY", 100.0, NOW, "RSI")
    assert account.holdings > 0
    account.execute("SELL", 100.0, NOW, "RSI")
    assert account.holdings < 0


def test_reset_restores_the_opening_balance(account):
    account.buy(100.0, NOW, quantity=10)
    account.reset()
    assert (account.holdings, account.balance, account.trades) == (0, 10_000, [])


def test_messages_use_the_account_currency():
    rupees = PaperTradingEngine(initial_capital=10_000, currency="INR")
    assert "₹" in rupees.buy(100.0, NOW, quantity=1)["message"]
    dollars = PaperTradingEngine(initial_capital=10_000, currency="USD")
    assert "$" in dollars.buy(100.0, NOW, quantity=1)["message"]


def test_performance_counts_only_closing_trades(account):
    account.buy(100.0, NOW, quantity=10)
    account.sell(120.0, NOW, quantity=10)
    account.buy(100.0, NOW, quantity=10)
    account.sell(90.0, NOW, quantity=10)
    stats = performance.summarise(account.trades, account.equity_curve, 10_000)
    assert stats["num_wins"] == 1
    assert stats["num_losses"] == 1
    assert stats["win_rate"] == pytest.approx(50.0)
    assert stats["best_trade"] == pytest.approx(200.0)
    assert stats["worst_trade"] == pytest.approx(-100.0)


def test_performance_of_an_untraded_account_is_empty():
    assert performance.summarise([], [], 10_000)["num_trades"] == 0


def test_performance_by_strategy_groups_closed_trades(account):
    account.buy(100.0, NOW, quantity=10, strategy="RSI")
    account.sell(120.0, NOW, quantity=10, strategy="RSI")
    table = performance.by_strategy(account.trades)
    assert table.loc[0, "Strategy"] == "RSI"
    assert table.loc[0, "Trades"] == 1
    assert table.loc[0, "Win Rate %"] == 100.0
