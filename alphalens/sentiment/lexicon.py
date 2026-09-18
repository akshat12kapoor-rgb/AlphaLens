"""A finance-tuned sentiment lexicon.

General-purpose word lists misread financial text: "liability" and "shares"
are neutral or negative in everyday English but routine here, while "beat",
"miss" and "guidance" carry strong directional meaning that generic lexicons
miss entirely. Weights run from -3 (strongly bearish) to +3 (strongly bullish).
"""

from __future__ import annotations

POSITIVE: dict[str, float] = {
    "beat": 2.0, "beats": 2.0, "smash": 2.5, "smashes": 2.5, "tops": 1.5,
    "exceed": 2.0, "exceeds": 2.0, "exceeded": 2.0, "outperform": 2.0,
    "surge": 2.5, "surges": 2.5, "surged": 2.5, "soar": 2.5, "soars": 2.5,
    "rally": 2.0, "rallies": 2.0, "rebound": 1.5, "rebounds": 1.5,
    "climb": 1.5, "climbs": 1.5, "gain": 1.5, "gains": 1.5, "jump": 1.5,
    "rise": 1.0, "rises": 1.0, "rose": 1.0, "up": 0.5, "higher": 1.0,
    "record": 1.5, "profit": 1.5, "profitable": 1.5, "growth": 1.5,
    "upgrade": 2.0, "upgrades": 2.0, "upgraded": 2.0, "bullish": 2.5,
    "buy": 1.5, "strong": 1.5, "robust": 1.5, "solid": 1.0, "boost": 1.5,
    "optimistic": 2.0, "optimism": 2.0, "confidence": 1.5, "hopeful": 1.0,
    "breakthrough": 2.0, "expansion": 1.0, "expands": 1.0, "accelerate": 1.5,
    "accelerates": 1.5, "accelerated": 1.5, "raised": 1.0, "hike": 1.0,
    "dividend": 0.5, "buyback": 1.5, "wins": 1.5, "won": 1.5, "secures": 1.5,
    "partnership": 1.0, "approval": 1.5, "approved": 1.5, "outlook": 0.5,
    "recovery": 1.5, "turnaround": 1.5, "inflows": 1.0, "demand": 0.5,
    "all-time": 1.5, "opportunity": 1.0, "efficient": 1.0, "innovation": 1.0,
}

NEGATIVE: dict[str, float] = {
    "miss": -2.0, "misses": -2.0, "missed": -2.0, "disappoint": -2.0,
    "disappoints": -2.0, "disappointing": -2.0, "underperform": -2.0,
    "plunge": -2.5, "plunges": -2.5, "plummet": -2.5, "tumble": -2.5,
    "tumbles": -2.5, "slump": -2.0, "slumps": -2.0, "crash": -3.0,
    "sink": -2.0, "sinks": -2.0, "slide": -1.5, "slides": -1.5, "slips": -1.5,
    "slip": -1.5, "fall": -1.5, "falls": -1.5, "fell": -1.5, "drop": -1.5,
    "drops": -1.5, "decline": -1.5, "declines": -1.5, "lower": -1.0,
    "down": -0.5, "loss": -2.0, "losses": -2.0, "deficit": -2.0,
    "downgrade": -2.0, "downgraded": -2.0, "bearish": -2.5, "sell": -1.5,
    "selloff": -2.0, "weak": -2.0, "weakness": -2.0, "sluggish": -1.5,
    "concern": -1.5, "concerns": -1.5, "worried": -1.5, "worries": -1.5,
    "fear": -2.0, "fears": -2.0, "risk": -1.0, "risks": -1.0, "warns": -1.5,
    "warning": -1.5, "lawsuit": -2.0, "probe": -1.5, "investigation": -2.0,
    "antitrust": -1.5, "regulators": -0.5, "restrictions": -1.5,
    "recall": -2.0, "halt": -2.0, "delay": -1.5, "delays": -1.5,
    "layoffs": -2.0, "cuts": -1.0, "slashes": -1.5, "pressure": -1.0,
    "headwinds": -1.5, "recession": -2.0, "inflation": -1.0, "volatile": -1.0,
    "uncertainty": -1.5, "overvalued": -2.0, "overextended": -1.5,
    "burn": -1.5, "widens": -1.0, "worsens": -2.0, "frustrated": -1.5,
    "threaten": -2.0, "threatens": -2.0, "intensifies": -1.0, "bankruptcy": -3.0,
}

# Words that flip the polarity of the term that follows.
NEGATORS: frozenset[str] = frozenset({
    "no", "not", "never", "none", "cannot", "cant", "wont", "without",
    "fails", "fail", "failed", "lacks", "lack", "avoids", "denies", "halts",
})

# Multipliers applied to the term that follows.
INTENSIFIERS: dict[str, float] = {
    "very": 1.5, "highly": 1.5, "extremely": 1.8, "sharply": 1.6,
    "significantly": 1.5, "substantially": 1.5, "major": 1.3, "massive": 1.7,
    "record": 1.4, "hugely": 1.7, "strongly": 1.4, "deeply": 1.4,
    "slightly": 0.5, "marginally": 0.5, "modestly": 0.6, "somewhat": 0.6,
}


def polarity(word: str) -> float:
    """Return the lexicon weight for a word, or 0.0 if it is not scored."""
    return POSITIVE.get(word, NEGATIVE.get(word, 0.0))


def size() -> dict[str, int]:
    return {
        "positive": len(POSITIVE),
        "negative": len(NEGATIVE),
        "negators": len(NEGATORS),
        "intensifiers": len(INTENSIFIERS),
    }
