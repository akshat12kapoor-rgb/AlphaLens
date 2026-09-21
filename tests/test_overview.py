"""The overview page's synthesis line: pure text logic, no Streamlit needed."""
from alphalens.ui.pages.overview import Read, _join, _takeaway


def test_join_formats_one_two_and_many_names():
    assert _join(["Valuation"]) == "Valuation"
    assert _join(["Valuation", "Sentiment"]) == "Valuation and Sentiment"
    assert _join(["Valuation", "Sentiment", "Technicals"]) == \
        "Valuation, Sentiment, and Technicals"


def test_takeaway_is_none_with_fewer_than_two_reads():
    assert _takeaway([]) is None
    assert _takeaway([None, None]) is None
    assert _takeaway([Read("Valuation", "bullish", "says BUY")]) is None


def test_takeaway_reports_agreement_when_every_lean_matches():
    reads = [Read("Valuation", "bullish", "says BUY (+20% to fair value)"),
             Read("Sentiment", "bullish", "reads bullish (+0.30)")]
    line = _takeaway(reads)
    assert "Valuation and Sentiment are bullish" in line
    assert "nothing above contradicts it" in line
    assert "disagree" not in line


def test_takeaway_reports_disagreement_when_leans_split():
    reads = [Read("Valuation", "bullish", "says BUY"),
             Read("Sentiment", "bearish", "reads bearish (-0.30)")]
    line = _takeaway(reads)
    assert "They disagree" in line
    assert "Valuation leans bullish" in line
    assert "Sentiment leans bearish" in line


def test_takeaway_reports_no_strong_lean_when_all_neutral_or_context():
    reads = [Read("Valuation", "neutral", "says HOLD"),
             Read("Backtest", "context", "has trend-following matching buy & hold")]
    line = _takeaway(reads)
    assert "None of them lean strongly either way right now." in line


def test_backtest_context_lean_never_counts_toward_agreement_or_disagreement():
    """Backtest measures strategy edge, not stock direction - it must show up
    in the sentence but never break a 2-way agreement into a false 3-way
    disagreement, and never manufacture agreement on its own."""
    reads = [Read("Valuation", "bullish", "says BUY"),
             Read("Sentiment", "bullish", "reads bullish"),
             Read("Backtest", "context", "has trend-following beating buy & hold")]
    line = _takeaway(reads)
    assert "disagree" not in line
    assert "Valuation and Sentiment are bullish" in line
    assert "Backtest" in line  # still shown, just not voted


def test_takeaway_includes_every_reads_detail_text():
    reads = [Read("Valuation", "bullish", "says BUY (+20% to fair value)"),
             Read("Sentiment", "neutral", "reads neutral (+0.02)")]
    line = _takeaway(reads)
    assert "**Valuation** says BUY (+20% to fair value)" in line
    assert "**Sentiment** reads neutral (+0.02)" in line
