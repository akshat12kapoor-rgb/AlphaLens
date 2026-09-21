"""
Reading a headline feed.

Feed files are one headline per line:

    2024-03-01 | AAPL | Apple beats quarterly earnings expectations

Blank lines and `#` comments are skipped; anything else rejects the whole
feed, naming every bad line, so a typo is a loud, unambiguous error rather
than a silently missing headline. This is deliberate, not an oversight: a
parser that skips bad lines and keeps going would make "half my headlines
went missing" indistinguishable from "the feed loaded cleanly" - a much
worse failure mode for something feeding a sentiment read than refusing to
guess at what a malformed line meant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from alphalens.core.config import SAMPLES

LINE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([A-Za-z.\-]{1,10})\s*\|\s*(.+?)\s*$")
SAMPLE_FEED = SAMPLES / "sample_headlines.txt"


@dataclass(frozen=True)
class Headline:
    date: date
    ticker: str
    text: str


def parse(text: str, source: str = "feed") -> list[Headline]:
    """Parse feed text into headlines, sorted by date then ticker.

    Every bad line is named, not just the first, and the error reports how
    many good headlines were found in between - so a large feed with one typo
    reads as "here's your one typo," not a reason to guess which subset of
    headlines silently made it through.
    """
    headlines, errors = [], []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE.match(line)
        if not match:
            errors.append((line_no, raw))
            continue
        day, ticker, headline = match.groups()
        headlines.append(Headline(date=datetime.strptime(day, "%Y-%m-%d").date(),
                                  ticker=ticker.upper(), text=headline))

    if errors:
        found = f" ({len(headlines)} good headline(s) found before rejecting the feed)" \
            if headlines else ""
        detail = "; ".join(
            f"line {n}: expected 'YYYY-MM-DD | TICKER | headline', got {raw!r}"
            for n, raw in errors)
        raise ValueError(f"{source}{found} - {detail}")

    headlines.sort(key=lambda h: (h.date, h.ticker))
    return headlines


def load(path: str | Path) -> list[Headline]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no such feed file: {path}")
    return parse(path.read_text(), source=path.name)


def sample() -> list[Headline]:
    """A mock feed of 34 headlines across 5 tickers, for trying the tool."""
    return load(SAMPLE_FEED)


def tickers(headlines: list[Headline]) -> list[str]:
    return sorted({h.ticker for h in headlines})


def for_ticker(headlines: list[Headline], ticker: str) -> list[Headline]:
    return [h for h in headlines if h.ticker == ticker.upper()]
