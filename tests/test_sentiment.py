"""Feed parsing and lexicon scoring (ported from SentimentFinance's suite)."""
from datetime import date

import pytest

from alphalens.sentiment.feed import Headline, for_ticker, load, parse, tickers
from alphalens.sentiment.scoring import score_headlines, score_text, tokenize

FEED = """\
# comment line

2024-03-01 | AAPL | Apple beats earnings expectations, revenue surges
2024-03-02 | aapl | Apple shares tumble on weak guidance
2024-03-01 | TSLA | Tesla deliveries miss estimates, stock plunges
"""


# ── tokenizing ──────────────────────────────────────────────────────────────

def test_lowercases_and_strips_punctuation():
    assert tokenize("Apple BEATS, revenue!") == ["apple", "beats", "revenue"]


def test_keeps_hyphens_and_apostrophes():
    assert tokenize("all-time high, company's") == ["all-time", "high", "company's"]


# ── scoring one headline ────────────────────────────────────────────────────

def test_positive_headline():
    score = score_text("Apple beats earnings expectations, revenue surges to record high")
    assert score.score > 0
    assert score.label == "bullish"


def test_negative_headline():
    score = score_text("Tesla deliveries miss estimates, stock plunges on weak demand")
    assert score.score < 0
    assert score.label == "bearish"


def test_neutral_when_nothing_matches():
    score = score_text("Company schedules its annual shareholder meeting for Tuesday")
    assert score.score == 0.0
    assert score.label == "neutral"
    assert score.hits == []


def test_negation_flips_polarity():
    plain = score_text("demand is strong")
    negated = score_text("demand is not strong")
    assert plain.score > 0
    assert negated.score < plain.score


def test_intensifier_before_term():
    assert score_text("orders sharply decline").score < score_text("orders decline").score


def test_intensifier_after_term():
    assert score_text("orders decline sharply").score < score_text("orders decline").score


def test_diminisher_dampens():
    assert score_text("shares slightly fall").score > score_text("shares fall").score


def test_intensifier_used_once():
    """A modifier between two scored terms amplifies only the first."""
    weights = dict(score_text("growth sharply beats").hits)
    assert weights["beats"] == 2.0
    assert weights["growth"] > 1.5


def test_score_stays_in_range():
    bullish = score_text(" ".join(["surges rally soars record profit growth"] * 20))
    bearish = score_text(" ".join(["crash plunges losses"] * 20))
    assert bullish.score <= 1.0
    assert bearish.score >= -1.0


def test_hits_report_matched_terms():
    matched = dict(score_text("Apple beats estimates but faces a lawsuit").hits)
    assert "beats" in matched
    assert matched["lawsuit"] < 0


def test_terms_render_for_display():
    assert "beats +2.0" in score_text("Apple beats estimates").terms
    assert score_text("nothing here").terms == "no scored terms"


# ── feeds ───────────────────────────────────────────────────────────────────

def test_parses_and_sorts():
    headlines = parse(FEED)
    assert len(headlines) == 3
    assert headlines[0].date == date(2024, 3, 1)
    assert [h.date for h in headlines] == sorted(h.date for h in headlines)


def test_ticker_uppercased():
    assert tickers(parse(FEED)) == ["AAPL", "TSLA"]


def test_filter_by_ticker():
    assert len(for_ticker(parse(FEED), "aapl")) == 2


def test_malformed_line_raises_with_its_line_number():
    with pytest.raises(ValueError, match="line 1"):
        parse("this is not a valid feed line\n")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "nope.txt")


def test_sample_feed_ships_with_the_platform():
    from alphalens.sentiment.feed import sample

    headlines = sample()
    assert len(headlines) == 34
    assert tickers(headlines) == ["AAPL", "BA", "JPM", "NVDA", "TSLA"]


# ── aggregation ─────────────────────────────────────────────────────────────

@pytest.fixture
def sentiments():
    return score_headlines(parse(FEED))


def test_groups_by_ticker(sentiments):
    assert sorted(sentiments) == ["AAPL", "TSLA"]
    assert len(sentiments["AAPL"].scores) == 2


def test_tsla_is_bearish(sentiments):
    assert sentiments["TSLA"].label == "BEARISH"


def test_counts_sum_to_headline_count(sentiments):
    aapl = sentiments["AAPL"]
    assert sum(aapl.counts.values()) == len(aapl.scores)


def test_momentum_within_scale(sentiments):
    for sentiment in sentiments.values():
        assert -1.0 <= sentiment.momentum <= 1.0


def test_momentum_zero_with_single_day(sentiments):
    assert sentiments["TSLA"].momentum == 0.0
    assert sentiments["TSLA"].momentum_word == "flat"


def test_confidence_low_on_small_sample(sentiments):
    assert sentiments["TSLA"].confidence == "low"


def test_sample_feed_scores_match_the_published_figures():
    """The numbers the CLI has always reported for the sample feed."""
    from alphalens.sentiment.feed import sample

    scored = score_headlines(sample())
    assert scored["AAPL"].mean == pytest.approx(0.2347, abs=0.0001)
    assert scored["AAPL"].label == "BULLISH"
    assert scored["AAPL"].confidence == "high"
    assert scored["BA"].mean == pytest.approx(-0.3319, abs=0.0001)
    assert scored["BA"].label == "BEARISH"


def test_momentum_reads_the_latest_day_against_the_earlier_ones():
    improving = score_headlines([
        Headline(date(2024, 1, 1), "X", "shares plunge on weak demand"),
        Headline(date(2024, 1, 2), "X", "shares surge on record profit"),
    ])["X"]
    assert improving.momentum > 0
    assert improving.momentum_word == "improving"
