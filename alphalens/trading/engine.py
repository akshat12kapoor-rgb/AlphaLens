"""
The paper-trading engine behind the simulator.

Position model: one signed holding.

    holdings > 0   long,  avg_entry_price is the average buy price
    holdings < 0   short, avg_entry_price is the average short price
    holdings == 0  flat

A BUY covers any open short first, then opens or adds to a long with whatever
is left; a SELL closes any open long first, then opens or adds to a short. A
flip is therefore recorded as two trades, which is what makes the trade log
readable. P&L works off one formula for both sides.

Shorting is collateralised by cash at 100%: a real broker uses Reg-T or SPAN
margin, so don't read position sizing here as realistic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from alphalens.core.config import DEFAULT_TRADE_FRACTION, INITIAL_CAPITAL
from alphalens.core.currency import money, signed_money


@dataclass
class Trade:
    """One execution. A flip writes two of these."""

    timestamp: object
    action: str  # BUY | SELL | SHORT | COVER
    price: float
    quantity: int
    total_value: float
    pnl: float = 0.0
    strategy: str = "Manual"
    balance_after: float = 0.0


CLOSING_ACTIONS = ("SELL", "COVER")


class PaperTradingEngine:
    """Virtual capital, positions and P&L for one replay session."""

    def __init__(self, initial_capital: float = INITIAL_CAPITAL, currency: str = "USD"):
        self.initial_capital = initial_capital
        self.currency = currency
        self.reset()

    def reset(self) -> None:
        self.balance: float = self.initial_capital
        self.holdings: int = 0
        self.avg_entry_price: float = 0.0
        self.realized_pnl: float = 0.0
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[object, float]] = []

    # ── execution ───────────────────────────────────────────────────────────

    def buy(self, price: float, timestamp: object, quantity: int | None = None,
            strategy: str = "Manual", fraction: float = DEFAULT_TRADE_FRACTION) -> dict:
        """Cover any short, then open or add to a long. Capped by available cash."""
        if quantity is None:
            quantity = max(1, int((self.balance * fraction) / price))
        affordable = int(self.balance / price) if price > 0 else 0
        quantity = min(quantity, affordable)
        if quantity <= 0:
            return {"success": False, "message": "Not enough cash to buy.", "actions": []}

        requested, messages, actions, realised = quantity, [], [], 0.0

        if self.holdings < 0:
            cover_qty = min(quantity, -self.holdings)
            cost = cover_qty * price
            pnl = (self.avg_entry_price - price) * cover_qty
            self.realized_pnl += pnl
            self.balance -= cost
            self.holdings += cover_qty
            if self.holdings == 0:
                self.avg_entry_price = 0.0
            self._record(timestamp, "COVER", price, cover_qty, cost, pnl, strategy)
            realised += pnl
            messages.append(f"Covered {cover_qty} short @ {money(price, self.currency)} "
                            f"({signed_money(pnl, self.currency)})")
            actions.append("COVER")
            quantity -= cover_qty

        if quantity > 0:
            cost = quantity * price
            if self.holdings > 0:
                self.avg_entry_price = (
                    (self.avg_entry_price * self.holdings) + cost) / (self.holdings + quantity)
            else:
                self.avg_entry_price = price
            self.balance -= cost
            self.holdings += quantity
            self._record(timestamp, "BUY", price, quantity, cost, 0.0, strategy)
            messages.append(f"Bought {quantity} @ {money(price, self.currency)}")
            actions.append("BUY")

        return {"success": True, "message": " · ".join(messages), "quantity": requested,
                "price": price, "pnl": realised, "actions": actions}

    def sell(self, price: float, timestamp: object, quantity: int | None = None,
             strategy: str = "Manual", fraction: float = DEFAULT_TRADE_FRACTION) -> dict:
        """Close any long, then open or add to a short with what is left."""
        if quantity is None:
            quantity = (self.holdings if self.holdings > 0
                        else max(1, int((self.balance * fraction) / price)))
        if quantity <= 0:
            return {"success": False, "message": "Nothing to sell.", "actions": []}

        requested, messages, actions, realised = quantity, [], [], 0.0

        if self.holdings > 0:
            close_qty = min(quantity, self.holdings)
            proceeds = close_qty * price
            pnl = (price - self.avg_entry_price) * close_qty
            self.realized_pnl += pnl
            self.balance += proceeds
            self.holdings -= close_qty
            if self.holdings == 0:
                self.avg_entry_price = 0.0
            self._record(timestamp, "SELL", price, close_qty, proceeds, pnl, strategy)
            realised += pnl
            messages.append(f"Sold {close_qty} @ {money(price, self.currency)} "
                            f"({signed_money(pnl, self.currency)})")
            actions.append("SELL")
            quantity -= close_qty

        if quantity > 0:
            # Size the short against cash on hand: the 100% collateral proxy.
            affordable = int(self.balance / price) if price > 0 else 0
            short_qty = min(quantity, affordable)
            if short_qty > 0:
                proceeds = short_qty * price
                if self.holdings < 0:
                    self.avg_entry_price = (
                        (self.avg_entry_price * -self.holdings) + proceeds
                    ) / (-self.holdings + short_qty)
                else:
                    self.avg_entry_price = price
                # Proceeds are credited and the holding goes negative, so
                # portfolio_value() nets the two and marks the short to market.
                self.balance += proceeds
                self.holdings -= short_qty
                self._record(timestamp, "SHORT", price, short_qty, proceeds, 0.0, strategy)
                messages.append(f"Shorted {short_qty} @ {money(price, self.currency)}")
                actions.append("SHORT")

        if not actions:
            return {"success": False, "message": "Not enough collateral to short.",
                    "actions": []}
        return {"success": True, "message": " · ".join(messages), "quantity": requested,
                "price": price, "pnl": realised, "actions": actions}

    def execute(self, signal: str, price: float, timestamp: object,
                strategy: str) -> dict | None:
        """Act on a strategy signal, flipping the position as the simulator does."""
        if signal == "BUY":
            if self.holdings < 0:
                self.buy(price, timestamp, quantity=-self.holdings, strategy=strategy)
            return self.buy(price, timestamp, strategy=strategy)
        if signal == "SELL":
            if self.holdings > 0:
                self.sell(price, timestamp, quantity=self.holdings, strategy=strategy)
            return self.sell(price, timestamp, strategy=strategy)
        return None

    # ── valuation of the book ───────────────────────────────────────────────

    def record_value(self, timestamp: object, price: float) -> None:
        self.equity_curve.append((timestamp, self.portfolio_value(price)))

    def portfolio_value(self, price: float) -> float:
        return self.balance + self.holdings * price

    def unrealized_pnl(self, price: float) -> float:
        if self.holdings == 0:
            return 0.0
        return (price - self.avg_entry_price) * self.holdings

    def snapshot(self, price: float) -> dict:
        value = self.portfolio_value(price)
        unrealised = self.unrealized_pnl(price)
        closed = [t for t in self.trades if t.action in CLOSING_ACTIONS]
        wins = [t for t in closed if t.pnl > 0]
        return {
            "portfolio_value": value,
            "total_pnl": self.realized_pnl + unrealised,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": unrealised,
            "return_pct": (value - self.initial_capital) / self.initial_capital * 100,
            "holdings": self.holdings,
            "cash": self.balance,
            "trades": len(self.trades),
            "closed_trades": len(closed),
            "win_rate": (len(wins) / len(closed) * 100) if closed else 0.0,
        }

    def _record(self, timestamp, action, price, quantity, value, pnl, strategy) -> None:
        self.trades.append(Trade(timestamp=timestamp, action=action, price=price,
                                 quantity=quantity, total_value=value, pnl=pnl,
                                 strategy=strategy, balance_after=self.balance))
