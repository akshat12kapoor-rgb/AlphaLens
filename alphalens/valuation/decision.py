"""
Turning two valuations into one call.

Blend the DCF and the multiples estimate, compare with the market price, and
apply a margin of safety so that small differences read as HOLD rather than a
false signal.
"""
from __future__ import annotations

from dataclasses import dataclass

from alphalens.core.config import DEFAULT_DCF_WEIGHT, MARGIN_OF_SAFETY
from alphalens.core.currency import money

VERDICTS = {
    "BUY": {"emoji": "🟢", "color": "#00C853"},
    "HOLD": {"emoji": "🟡", "color": "#FFD600"},
    "SELL": {"emoji": "🔴", "color": "#FF5252"},
}


@dataclass(frozen=True)
class Verdict:
    symbol: str
    currency: str
    current_price: float
    dcf_value: float
    multiples_value: float | None
    fair_value: float
    upside: float
    decision: str
    dcf_weight: float
    multiples_weight: float
    margin_of_safety: float = MARGIN_OF_SAFETY

    @property
    def emoji(self) -> str:
        return VERDICTS[self.decision]["emoji"]

    @property
    def color(self) -> str:
        return VERDICTS[self.decision]["color"]

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.decision}"

    def describe(self) -> str:
        price = money(self.current_price, self.currency)
        fair = money(self.fair_value, self.currency)
        if self.decision == "HOLD":
            return (f"{self.emoji} HOLD — {self.symbol} is fairly valued "
                    f"({self.upside:+.1%} vs fair value {fair})")
        direction = "undervalued" if self.upside > 0 else "overvalued"
        return (f"{self.emoji} {self.decision} — {self.symbol} appears {direction} by "
                f"{abs(self.upside):.1%} (market {price} | fair value {fair})")

    def breakdown(self) -> dict[str, float]:
        rows = {"Current Price": self.current_price, "DCF Value": self.dcf_value,
                "Blended Value": self.fair_value}
        if self.multiples_value is not None:
            rows["Multiples Value"] = self.multiples_value
        return rows


def decide(symbol: str, current_price: float, dcf_value: float,
           multiples_value: float | None, currency: str = "USD",
           dcf_weight: float = DEFAULT_DCF_WEIGHT,
           margin_of_safety: float = MARGIN_OF_SAFETY) -> Verdict:
    """Blend, compare, classify. With no multiples estimate the DCF carries it."""
    multiples_weight = 1.0 - dcf_weight
    if multiples_value is not None and multiples_value > 0:
        fair_value = dcf_value * dcf_weight + multiples_value * multiples_weight
    else:
        fair_value, dcf_weight, multiples_weight = dcf_value, 1.0, 0.0
    fair_value = max(fair_value, 0.0)

    upside = (fair_value - current_price) / current_price if current_price > 0 else 0.0
    if upside > margin_of_safety:
        decision = "BUY"
    elif upside < -margin_of_safety:
        decision = "SELL"
    else:
        decision = "HOLD"

    return Verdict(symbol=symbol, currency=currency, current_price=current_price,
                   dcf_value=dcf_value, multiples_value=multiples_value,
                   fair_value=fair_value, upside=upside, decision=decision,
                   dcf_weight=dcf_weight, multiples_weight=multiples_weight,
                   margin_of_safety=margin_of_safety)
