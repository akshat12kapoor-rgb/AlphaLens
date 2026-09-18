"""
Comparable-company valuation.

Two market multiples, applied to sector medians when a real comparable table
isn't available:

    P/E        implied price = EPS x sector P/E
    EV/EBITDA  implied EV    = EBITDA x sector EV/EBITDA
               equity value  = EV - debt + cash
               implied price = equity value / shares

Sector medians are long-run figures (Damodaran, Bloomberg), not live comps.
"""
from __future__ import annotations

from dataclasses import dataclass

SECTOR_MULTIPLES: dict[str, dict[str, float]] = {
    "Technology": {"pe": 28.0, "ev_ebitda": 20.0},
    "Communication Services": {"pe": 22.0, "ev_ebitda": 14.0},
    "Consumer Discretionary": {"pe": 25.0, "ev_ebitda": 15.0},
    "Consumer Cyclical": {"pe": 25.0, "ev_ebitda": 15.0},
    "Consumer Staples": {"pe": 22.0, "ev_ebitda": 14.0},
    "Consumer Defensive": {"pe": 22.0, "ev_ebitda": 14.0},
    "Energy": {"pe": 12.0, "ev_ebitda": 7.0},
    "Financials": {"pe": 13.0, "ev_ebitda": 9.0},
    "Financial Services": {"pe": 13.0, "ev_ebitda": 9.0},
    "Health Care": {"pe": 22.0, "ev_ebitda": 14.0},
    "Healthcare": {"pe": 22.0, "ev_ebitda": 14.0},
    "Industrials": {"pe": 20.0, "ev_ebitda": 13.0},
    "Materials": {"pe": 16.0, "ev_ebitda": 10.0},
    "Basic Materials": {"pe": 16.0, "ev_ebitda": 10.0},
    "Real Estate": {"pe": 40.0, "ev_ebitda": 18.0},
    "Utilities": {"pe": 18.0, "ev_ebitda": 11.0},
}

#: Broad-market fallback for unknown or missing sectors.
DEFAULT_MULTIPLES = {"pe": 20.0, "ev_ebitda": 12.0}


@dataclass(frozen=True)
class MultiplesResult:
    pe_multiple: float
    ev_ebitda_multiple: float
    pe_implied_price: float | None
    ev_implied_price: float | None
    blended_price: float | None
    methods: list[str]


def for_sector(sector: str | None) -> dict[str, float]:
    return SECTOR_MULTIPLES.get(sector or "", DEFAULT_MULTIPLES)


def run(eps: float | None, ebitda: float | None, total_debt: float, cash: float,
        shares_outstanding: float | None, sector: str | None,
        pe_override: float | None = None,
        ev_ebitda_override: float | None = None) -> MultiplesResult:
    """Blend whichever multiples the company's data supports."""
    sector_multiples = for_sector(sector)
    pe = pe_override if pe_override is not None else sector_multiples["pe"]
    ev_ebitda = (ev_ebitda_override if ev_ebitda_override is not None
                 else sector_multiples["ev_ebitda"])

    pe_price = _from_earnings(eps, pe)
    ev_price = _from_ebitda(ebitda, total_debt, cash, shares_outstanding, ev_ebitda)

    available = [p for p in (pe_price, ev_price) if p is not None and p > 0]
    methods = [name for name, price in (("P/E", pe_price), ("EV/EBITDA", ev_price))
               if price is not None and price > 0]

    return MultiplesResult(
        pe_multiple=pe, ev_ebitda_multiple=ev_ebitda, pe_implied_price=pe_price,
        ev_implied_price=ev_price,
        blended_price=(sum(available) / len(available)) if available else None,
        methods=methods)


def _from_earnings(eps: float | None, multiple: float) -> float | None:
    """None for loss-makers: a negative P/E implies a negative price."""
    if eps is None or eps <= 0:
        return None
    return eps * multiple


def _from_ebitda(ebitda: float | None, total_debt: float, cash: float,
                 shares: float | None, multiple: float) -> float | None:
    if not ebitda or ebitda <= 0 or not shares or shares <= 0:
        return None
    equity_value = ebitda * multiple - total_debt + cash
    price = equity_value / shares
    return price if price > 0 else None
