"""
Reading a headline feed.

Feed files are one headline per line:

    2024-03-01 | AAPL | Apple beats quarterly earnings expectations

Blank lines and `#` comments are skipped; anything else raises with its line
number, so a typo is a clear error rather than a silently missing headline.
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
    """Parse feed text into headlines, sorted by date then ticker."""
    headlines = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE.match(line)
        if not match:
            raise ValueError(
                f"{source} line {line_no}: expected 'YYYY-MM-DD | TICKER | headline', "
                f"got {raw!r}")
        day, ticker, headline = match.groups()
        headlines.append(Headline(date=datetime.strptime(day, "%Y-%m-%d").date(),
                                  ticker=ticker.upper(), text=headline))
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
