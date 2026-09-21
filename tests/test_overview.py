"""The overview page's synthesis line: pure text logic, no Streamlit needed."""
import pandas as pd

from alphalens.ui.context import Attempt
from alphalens.ui.pages.overview import Read, export_markdown, join_names, takeaway


def test_join_formats_one_two_and_many_names():
    assert join_names(["Valuation"]) == "Valuation"
    assert join_names(["Valuation", "Sentiment"]) == "Valuation and Sentiment"
    assert join_names(["Valuation", "Sentiment", "Technicals"]) == \
        "Valuation, Sentiment, and Technicals"


def test_takeaway_is_none_with_fewer_than_two_reads():
    assert takeaway([]) is None
    assert takeaway([None, None]) is None
    assert takeaway([Read("Valuation", "bullish", "says BUY")]) is None


def test_takeaway_reports_agreement_when_every_lean_matches():
    reads = [Read("Valuation", "bullish", "says BUY (+20% to fair value)"),
             Read("Sentiment", "bullish", "reads bullish (+0.30)")]
    line = takeaway(reads)
    assert "Valuation and Sentiment are bullish" in line
    assert "nothing above contradicts it" in line
    assert "disagree" not in line


def test_takeaway_reports_disagreement_when_leans_split():
    reads = [Read("Valuation", "bullish", "says BUY"),
             Read("Sentiment", "bearish", "reads bearish (-0.30)")]
    line = takeaway(reads)
    assert "They disagree" in line
    assert "Valuation leans bullish" in line
    assert "Sentiment leans bearish" in line


def test_takeaway_reports_no_strong_lean_when_all_neutral_or_context():
    reads = [Read("Valuation", "neutral", "says HOLD"),
             Read("Backtest", "context", "has trend-following matching buy & hold")]
    line = takeaway(reads)
    assert "None of them lean strongly either way right now." in line


def test_backtest_context_lean_never_counts_toward_agreement_or_disagreement():
    """Backtest measures strategy edge, not stock direction - it must show up
    in the sentence but never break a 2-way agreement into a false 3-way
    disagreement, and never manufacture agreement on its own."""
    reads = [Read("Valuation", "bullish", "says BUY"),
             Read("Sentiment", "bullish", "reads bullish"),
             Read("Backtest", "context", "has trend-following beating buy & hold")]
    line = takeaway(reads)
    assert "disagree" not in line
    assert "Valuation and Sentiment are bullish" in line
    assert "Backtest" in line  # still shown, just not voted


def test_takeaway_includes_every_reads_detail_text():
    reads = [Read("Valuation", "bullish", "says BUY (+20% to fair value)"),
             Read("Sentiment", "neutral", "reads neutral (+0.02)")]
    line = takeaway(reads)
    assert "**Valuation** says BUY (+20% to fair value)" in line
    assert "**Sentiment** reads neutral (+0.02)" in line


# ── export ───────────────────────────────────────────────────────────────────

def test_export_markdown_includes_price_reads_and_takeaway():
    history = Attempt(True, pd.DataFrame({"close": [100.0, 105.0]}))
    reads = [Read("Valuation", "bullish", "says BUY (+20% to fair value)"),
             Read("Sentiment", "bullish", "reads bullish (+0.30)")]
    text = export_markdown("AAPL", "Apple Inc.", history, reads)
    assert "Apple Inc. (AAPL)" in text
    assert "Last close: 105.00" in text
    assert "**Valuation**: says BUY (+20% to fair value)" in text
    assert "Valuation and Sentiment are bullish" in text


def test_export_markdown_handles_missing_price_and_no_takeaway():
    history = Attempt(False, error="rate limited")
    text = export_markdown("AAPL", "Apple Inc.", history, [None, None])
    assert "Last close" not in text
    assert "Takeaway" not in text
