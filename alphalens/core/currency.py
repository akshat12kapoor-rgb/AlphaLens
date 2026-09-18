"""
Currency handling.

Every tool shows prices in the instrument's own currency. Yahoo reports it per
symbol (`Fundamentals.currency` / `Quote.currency`), so nothing here guesses
from the ticker suffix unless the feed gives us nothing to work with.
"""
from __future__ import annotations

SYMBOLS: dict[str, str] = {
    "USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "GBp": "p", "JPY": "¥",
    "CNY": "¥", "HKD": "HK$", "AUD": "A$", "CAD": "C$", "CHF": "CHF ",
    "SGD": "S$", "KRW": "₩", "BRL": "R$", "ZAR": "R", "SEK": "kr ",
}

#: Exchange suffix -> currency, used only when Yahoo reports nothing.
SUFFIXES: dict[str, str] = {
    ".NS": "INR", ".BO": "INR", ".L": "GBp", ".DE": "EUR", ".PA": "EUR",
    ".AS": "EUR", ".MI": "EUR", ".SW": "CHF", ".T": "JPY", ".HK": "HKD",
    ".AX": "AUD", ".TO": "CAD", ".SI": "SGD", ".KS": "KRW", ".SA": "BRL",
    ".JO": "ZAR", ".ST": "SEK",
}

DEFAULT_CURRENCY = "USD"


def guess_currency(symbol: str) -> str:
    """Fallback for when Yahoo doesn't report a currency."""
    upper = symbol.upper()
    for suffix, code in SUFFIXES.items():
        if upper.endswith(suffix.upper()):
            return code
    return DEFAULT_CURRENCY


def symbol_for(currency: str | None) -> str:
    """The display symbol for a currency code, e.g. 'INR' -> '₹'.

    Unknown codes fall back to the code itself ('PLN ') so figures are never
    shown under the wrong symbol.
    """
    if not currency:
        return SYMBOLS[DEFAULT_CURRENCY]
    return SYMBOLS.get(currency, f"{currency} ")


def money(value: float | None, currency: str | None, decimals: int = 2) -> str:
    """Format an amount in its own currency: money(1234.5, "INR") -> '₹1,234.50'."""
    if value is None:
        return "—"
    return f"{symbol_for(currency)}{value:,.{decimals}f}"


def signed_money(value: float | None, currency: str | None, decimals: int = 0) -> str:
    """Signed amount, for P&L: '+₹1,234' / '−₹1,234'."""
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "−"
    return f"{sign}{symbol_for(currency)}{abs(value):,.{decimals}f}"


def compact_money(value: float | None, currency: str | None) -> str:
    """Large amounts in billions/millions: '$416.16B'."""
    if value is None:
        return "—"
    prefix = symbol_for(currency)
    magnitude = abs(value)
    if magnitude >= 1e12:
        return f"{prefix}{value / 1e12:,.2f}T"
    if magnitude >= 1e9:
        return f"{prefix}{value / 1e9:,.2f}B"
    if magnitude >= 1e6:
        return f"{prefix}{value / 1e6:,.2f}M"
    return f"{prefix}{value:,.2f}"
