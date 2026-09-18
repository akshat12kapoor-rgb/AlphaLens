"""
The single Yahoo Finance boundary for the whole platform.

Every tool reads prices, fundamentals and news through here, so they always
agree with each other, and a test or offline run can replace one function and
change what the entire app sees.

yfinance is imported lazily: the CLIs and most tests never touch the network.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from alphalens.core.currency import guess_currency
from alphalens.data.cache import cached
from alphalens.data.models import DataUnavailable, Fundamentals, Quote, Story

OHLCV = ["open", "high", "low", "close", "volume"]

#: Yahoo only serves intraday bars for a recent window.
INTRADAY_LIMIT_DAYS = {"1m": 7, "5m": 60, "15m": 60, "30m": 60, "1h": 730}

#: Periods Yahoo actually supports per interval.
PERIODS = {
    "1m": ["1d", "5d", "7d"],
    "5m": ["5d", "1mo"],
    "15m": ["5d", "1mo"],
    "30m": ["5d", "1mo"],
    "1h": ["1mo", "3mo", "6mo", "1y", "2y"],
    "1d": ["3mo", "6mo", "1y", "2y", "5y", "10y"],
    "1wk": ["1y", "2y", "5y", "10y", "max"],
}


def periods_for(interval: str) -> list[str]:
    return PERIODS.get(interval, ["3mo", "6mo", "1y"])


def _ticker(symbol: str):
    import yfinance as yf

    return yf.Ticker(symbol.upper().strip())


# ── prices ──────────────────────────────────────────────────────────────────

@cached()
def prices(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """OHLCV bars, lowercase columns, tz-naive index, zero-volume bars dropped.

    Raises DataUnavailable with Yahoo's interval limit spelled out, which is the
    usual cause of an empty intraday response.
    """
    try:
        raw = _ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001 - yfinance raises a wide variety
        raise DataUnavailable(f"Could not fetch prices for {symbol!r}: {exc}") from exc

    if raw.empty:
        limit = INTRADAY_LIMIT_DAYS.get(interval)
        if limit:
            raise DataUnavailable(
                f"No {interval} data for {symbol!r} over {period}. Yahoo only serves "
                f"{interval} bars for the last {limit} days - use a longer interval."
            )
        raise DataUnavailable(f"No data for {symbol!r}. Check the symbol.")

    frame = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    frame.columns = OHLCV
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame.dropna().sort_index()
    frame = frame[frame["volume"] > 0]
    if frame.empty:
        raise DataUnavailable(f"No tradable bars for {symbol!r} over {period}.")
    return frame


# ── quote ───────────────────────────────────────────────────────────────────

@cached()
def quote(symbol: str) -> Quote:
    """Name, currency and last price. The currency here is what every tool
    formats with, so it is never guessed when Yahoo reports one."""
    info = _info(symbol)
    return Quote(
        symbol=symbol.upper(),
        name=_first(info, ["longName", "shortName"]) or symbol.upper(),
        currency=info.get("currency") or guess_currency(symbol),
        sector=info.get("sector"),
        industry=info.get("industry"),
        price=_price(symbol, info),
        exchange=info.get("exchange"),
        market_cap=info.get("marketCap"),
    )


# ── fundamentals ────────────────────────────────────────────────────────────

@cached()
def fundamentals(symbol: str) -> Fundamentals:
    """Normalise Yahoo's statements into the fields the valuation models need.

    Yahoo names statement rows inconsistently across companies, so each figure
    is looked up under several aliases and left as None when absent.
    """
    info = _info(symbol)
    stock = _ticker(symbol)
    income = _statement(stock, "income_stmt")
    cashflow = _statement(stock, "cashflow")
    balance = _statement(stock, "balance_sheet")

    revenue_history = _row(income, ["Total Revenue", "Operating Revenue", "Revenue"])
    fcf_history = _free_cash_flow(cashflow)

    return Fundamentals(
        symbol=symbol.upper(),
        name=_first(info, ["longName", "shortName"]) or symbol.upper(),
        currency=info.get("financialCurrency") or info.get("currency") or guess_currency(symbol),
        price=_price(symbol, info),
        shares_outstanding=info.get("sharesOutstanding"),
        revenue=_latest(revenue_history) or info.get("totalRevenue"),
        free_cash_flow=_latest(fcf_history) or info.get("freeCashflow"),
        ebitda=_latest(_row(income, ["EBITDA", "Normalized EBITDA"])) or info.get("ebitda"),
        net_income=(_latest(_row(income, ["Net Income", "Net Income Common Stockholders"]))
                    or info.get("netIncomeToCommon")),
        eps=_first(info, ["trailingEps", "epsTrailingTwelveMonths"]),
        total_debt=(_latest(_row(balance, ["Total Debt", "Long Term Debt"]))
                    or info.get("totalDebt") or 0.0),
        cash=(_latest(_row(balance, ["Cash And Cash Equivalents",
                                     "Cash Cash Equivalents And Short Term Investments"]))
              or info.get("totalCash") or 0.0),
        sector=info.get("sector"),
        industry=info.get("industry"),
        revenue_history=revenue_history,
        fcf_history=fcf_history,
    )


# ── news ────────────────────────────────────────────────────────────────────

def fetch_news(symbol: str) -> list[Story]:
    """Recent Yahoo stories. Yahoo's feed for a ticker can include broader
    market pieces, not only company news."""
    try:
        items = _ticker(symbol).news or []
    except Exception as exc:  # noqa: BLE001
        raise DataUnavailable(f"Could not fetch news for {symbol!r}: {exc}") from exc

    stories: list[Story] = []
    for item in items:
        content = item.get("content") or item
        title = (content.get("title") or "").strip()
        stamp = content.get("pubDate") or content.get("displayTime")
        if not title or not stamp:
            continue
        try:
            published = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        stories.append(Story(
            title=title,
            published=published,
            publisher=(content.get("provider") or {}).get("displayName", ""),
            url=((content.get("canonicalUrl") or {}).get("url")
                 or (content.get("clickThroughUrl") or {}).get("url") or ""),
        ))
    return sorted(stories, key=lambda s: s.published)


@cached()
def news(symbol: str) -> list[Story]:
    # Resolved at call time so offline runs and tests can replace fetch_news.
    return globals()["fetch_news"](symbol)


# ── helpers ─────────────────────────────────────────────────────────────────

def _info(symbol: str) -> dict:
    try:
        return _ticker(symbol).info or {}
    except Exception:  # noqa: BLE001 - a missing profile is not fatal
        return {}


def _price(symbol: str, info: dict) -> float | None:
    value = _first(info, ["currentPrice", "regularMarketPrice", "previousClose"])
    if value:
        return float(value)
    try:
        history = _ticker(symbol).history(period="5d")
        if not history.empty:
            return float(history["Close"].iloc[-1])
    except Exception:  # noqa: BLE001
        pass
    return None


def _first(info: dict, keys: list[str]):
    for key in keys:
        value = info.get(key)
        if value not in (None, "", 0):
            return value
    return None


def _statement(stock, attribute: str) -> pd.DataFrame:
    try:
        frame = getattr(stock, attribute)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _row(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    """A statement row by any of its aliases, oldest first, indexed by year."""
    if frame.empty:
        return pd.Series(dtype="float64")
    for name in names:
        if name in frame.index:
            series = frame.loc[name].dropna().astype("float64")
            if series.empty:
                continue
            series = series.iloc[::-1]
            series.index = [str(getattr(i, "year", i)) for i in series.index]
            return series
    return pd.Series(dtype="float64")


def _free_cash_flow(cashflow: pd.DataFrame) -> pd.Series:
    """Free cash flow: Yahoo's own row when present, else operating cash flow
    less capital expenditure."""
    direct = _row(cashflow, ["Free Cash Flow"])
    if not direct.empty:
        return direct
    operating = _row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    capex = _row(cashflow, ["Capital Expenditure", "Capital Expenditures"])
    if operating.empty:
        return pd.Series(dtype="float64")
    if capex.empty:
        return operating
    common = operating.index.intersection(capex.index)
    # Capex is reported negative, so adding it subtracts the spend.
    return (operating[common] + capex[common]).astype("float64")


def _latest(series: pd.Series) -> float | None:
    if series is None or series.empty:
        return None
    return float(series.iloc[-1])
