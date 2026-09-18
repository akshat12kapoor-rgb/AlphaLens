"""
Scoring headlines with the finance lexicon.

How one headline is scored:

1. Split into lowercase words.
2. Look up each word's weight.
3. Apply an adjacent intensifier - headlines put them on either side ("sharply
   lower", "orders decline sharply"), so both neighbours are checked and each
   modifier is used once.
4. Flip the sign if a negator appears within the previous two words.
5. Sum, then squash with tanh into [-1, 1], so a long headline cannot outweigh a
   short one on word count alone.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from alphalens.sentiment.feed import Headline
from alphalens.sentiment.lexicon import INTENSIFIERS, NEGATORS, polarity

TOKEN = re.compile(r"[a-z][a-z'\-]*")
NEGATION_WINDOW = 2
#: Raw score at which the squashed score reaches about 0.76.
SQUASH = 4.0
BULLISH, BEARISH = 0.15, -0.15
#: Momentum beyond this reads as improving or deteriorating rather than flat.
MOMENTUM_BAND = 0.05


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Score:
    """The sentiment of a single headline."""

    text: str
    raw: float
    score: float
    hits: list[tuple[str, float]] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= BULLISH:
            return "bullish"
        if self.score <= BEARISH:
            return "bearish"
        return "neutral"

    @property
    def terms(self) -> str:
        return ", ".join(f"{word} {weight:+.1f}" for word, weight in self.hits) \
            or "no scored terms"


def score_text(text: str) -> Score:
    tokens = tokenize(text)
    total, hits, used = 0.0, [], set()

    for i, token in enumerate(tokens):
        weight = polarity(token)
        if weight == 0.0:
            continue

        for neighbour in (i - 1, i + 1):
            if 0 <= neighbour < len(tokens) and neighbour not in used:
                multiplier = INTENSIFIERS.get(tokens[neighbour])
                if multiplier is not None:
                    weight *= multiplier
                    used.add(neighbour)
                    break

        if any(t in NEGATORS for t in tokens[max(0, i - NEGATION_WINDOW):i]):
            weight = -weight

        total += weight
        hits.append((token, round(weight, 2)))

    return Score(text=text, raw=round(total, 3),
                 score=round(math.tanh(total / SQUASH), 4), hits=hits)


@dataclass(frozen=True)
class TickerSentiment:
    """Aggregate sentiment for one ticker."""

    ticker: str
    scores: list[Score]
    by_day: dict[date, float]

    @property
    def mean(self) -> float:
        return sum(s.score for s in self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def label(self) -> str:
        if self.mean >= BULLISH:
            return "BULLISH"
        if self.mean <= BEARISH:
            return "BEARISH"
        return "NEUTRAL"

    @property
    def counts(self) -> dict[str, int]:
        out = {"bullish": 0, "neutral": 0, "bearish": 0}
        for score in self.scores:
            out[score.label] += 1
        return out

    @property
    def momentum(self) -> float:
        """The latest day's tone against the mean of the days before it.

        Often more informative than the level, since the level reflects news the
        market has already seen. The difference of two values in [-1, 1] spans
        [-2, 2], so it is halved to stay on the same scale as `mean`.
        """
        if len(self.by_day) < 2:
            return 0.0
        days = sorted(self.by_day)
        earlier = [self.by_day[d] for d in days[:-1]]
        return round((self.by_day[days[-1]] - sum(earlier) / len(earlier)) / 2, 4)

    @property
    def momentum_word(self) -> str:
        if self.momentum > MOMENTUM_BAND:
            return "improving"
        if self.momentum < -MOMENTUM_BAND:
            return "deteriorating"
        return "flat"

    @property
    def confidence(self) -> str:
        """How much to trust the reading, from sample size and agreement."""
        count = len(self.scores)
        if count < 3:
            return "low"
        agreement = max(self.counts.values()) / count
        if count >= 6 and agreement >= 0.6:
            return "high"
        return "medium" if agreement >= 0.5 else "low"


def score_headlines(headlines: list[Headline]) -> dict[str, TickerSentiment]:
    """Score every headline and aggregate per ticker."""
    scores: dict[str, list[Score]] = defaultdict(list)
    daily: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(list))

    for headline in headlines:
        score = score_text(headline.text)
        scores[headline.ticker].append(score)
        daily[headline.ticker][headline.date].append(score.score)

    return {
        ticker: TickerSentiment(
            ticker=ticker, scores=ticker_scores,
            by_day={day: round(sum(values) / len(values), 4)
                    for day, values in sorted(daily[ticker].items())})
        for ticker, ticker_scores in scores.items()
    }
