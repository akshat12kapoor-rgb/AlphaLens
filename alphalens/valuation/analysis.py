"""
The whole valuation pipeline behind one call.

The overview card and the valuation page both go through `value()`, so a
summary can never disagree with the page it summarises.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from alphalens.core.config import DEFAULT_DCF_WEIGHT
from alphalens.data.models import Fundamentals
from alphalens.valuation import dcf, decision, multiples


@dataclass(frozen=True)
class Assumptions:
    """Everything the user can change on the valuation page."""

    growth_rate: float = 0.10
    stage1_years: int = 5
    stage2_years: int = 0
    wacc: float = 0.10
    terminal_growth: float = 0.03
    dcf_weight: float = DEFAULT_DCF_WEIGHT
    pe_override: float | None = None
    ev_ebitda_override: float | None = None

    def with_(self, **changes) -> "Assumptions":
        return replace(self, **changes)


#: What the valuation page shows before anything is touched.
DEFAULTS = Assumptions()


@dataclass(frozen=True)
class Valuation:
    fundamentals: Fundamentals
    assumptions: Assumptions
    dcf: dcf.DCFResult
    multiples: multiples.MultiplesResult
    verdict: decision.Verdict


def value(data: Fundamentals, assumptions: Assumptions = DEFAULTS) -> Valuation:
    """Run the DCF and the comparables, then blend them into a verdict.

    Raises MissingData when the company lacks what a DCF needs (crypto and most
    ETFs), which callers show as "unavailable" rather than a broken page.
    """
    data.require("free_cash_flow", "shares_outstanding", "price")

    dcf_result = dcf.run(
        base_fcf=data.free_cash_flow, shares_outstanding=data.shares_outstanding,
        growth_rate=assumptions.growth_rate, wacc=assumptions.wacc,
        terminal_growth=assumptions.terminal_growth,
        stage1_years=assumptions.stage1_years, stage2_years=assumptions.stage2_years)

    multiples_result = multiples.run(
        eps=data.eps, ebitda=data.ebitda, total_debt=data.total_debt, cash=data.cash,
        shares_outstanding=data.shares_outstanding, sector=data.sector,
        pe_override=assumptions.pe_override,
        ev_ebitda_override=assumptions.ev_ebitda_override)

    verdict = decision.decide(
        symbol=data.symbol, current_price=data.price,
        dcf_value=dcf_result.intrinsic_value,
        multiples_value=multiples_result.blended_price,
        currency=data.currency, dcf_weight=assumptions.dcf_weight)

    return Valuation(fundamentals=data, assumptions=assumptions, dcf=dcf_result,
                     multiples=multiples_result, verdict=verdict)
