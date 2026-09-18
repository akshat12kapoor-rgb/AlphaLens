"""DCF, comparables and the verdict that blends them."""
import pytest

from alphalens.data.models import Fundamentals, MissingData
from alphalens.valuation import analysis, dcf, decision, multiples


# ── DCF ─────────────────────────────────────────────────────────────────────

def test_single_year_dcf_matches_the_arithmetic():
    """One year of 10% growth at a 10% discount rate, terminal growth 5%:
    FCF1 = 110, PV = 100, TV = 110*1.05/0.05 = 2310, PV(TV) = 2100."""
    result = dcf.run(base_fcf=100, shares_outstanding=10, growth_rate=0.10,
                     wacc=0.10, terminal_growth=0.05, stage1_years=1, stage2_years=0)
    assert result.projected_fcf == pytest.approx([110.0])
    assert result.present_values == pytest.approx([100.0])
    assert result.terminal_value == pytest.approx(2310.0)
    assert result.pv_terminal_value == pytest.approx(2100.0)
    assert result.intrinsic_value == pytest.approx(220.0)


def test_stage_two_fades_growth_to_the_terminal_rate():
    result = dcf.run(base_fcf=100, shares_outstanding=1, growth_rate=0.20, wacc=0.10,
                     terminal_growth=0.02, stage1_years=2, stage2_years=3)
    assert result.growth_rates[:2] == pytest.approx([0.20, 0.20])
    assert result.growth_rates[-1] == pytest.approx(0.02)
    assert result.growth_rates[2] > result.growth_rates[3] > result.growth_rates[4]


def test_a_higher_discount_rate_lowers_the_value():
    cheap = dcf.run(100, 10, 0.10, 0.08, 0.03).intrinsic_value
    dear = dcf.run(100, 10, 0.10, 0.14, 0.03).intrinsic_value
    assert dear < cheap


def test_discount_rate_must_exceed_terminal_growth():
    with pytest.raises(ValueError, match="terminal growth"):
        dcf.run(100, 10, 0.10, 0.03, 0.05)


@pytest.mark.parametrize("kwargs, message", [
    (dict(wacc=-0.1, terminal_growth=0.02), "positive"),
    (dict(wacc=0.1, terminal_growth=-0.01), "negative"),
])
def test_invalid_rates_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        dcf.validate(**kwargs)


def test_dcf_needs_cash_flow_and_a_share_count():
    with pytest.raises(ValueError, match="free cash flow"):
        dcf.run(0, 10, 0.1, 0.1, 0.03)
    with pytest.raises(ValueError, match="share count"):
        dcf.run(100, 0, 0.1, 0.1, 0.03)


def test_sensitivity_grid_rises_as_growth_rises(fundamentals):
    grid = dcf.sensitivity(fundamentals.free_cash_flow, fundamentals.shares_outstanding,
                           terminal_growth=0.03)
    first_row = grid.iloc[0].dropna()
    assert list(first_row) == sorted(first_row)


# ── multiples ───────────────────────────────────────────────────────────────

def test_pe_valuation_is_eps_times_the_multiple():
    result = multiples.run(eps=10, ebitda=None, total_debt=0, cash=0,
                           shares_outstanding=100, sector="Technology")
    assert result.pe_implied_price == pytest.approx(280.0)  # 10 x 28
    assert result.methods == ["P/E"]


def test_loss_makers_have_no_pe_estimate():
    result = multiples.run(eps=-2, ebitda=None, total_debt=0, cash=0,
                           shares_outstanding=100, sector="Technology")
    assert result.pe_implied_price is None
    assert result.blended_price is None


def test_ev_ebitda_bridges_debt_and_cash():
    """EV = 100 x 12 = 1200; equity = 1200 - 300 + 100 = 1000; over 100 shares = 10."""
    result = multiples.run(eps=None, ebitda=100, total_debt=300, cash=100,
                           shares_outstanding=100, sector=None)
    assert result.ev_implied_price == pytest.approx(10.0)


def test_blend_averages_the_available_methods():
    result = multiples.run(eps=10, ebitda=100, total_debt=0, cash=0,
                           shares_outstanding=100, sector=None)
    assert result.methods == ["P/E", "EV/EBITDA"]
    assert result.blended_price == pytest.approx((200.0 + 12.0) / 2)


def test_overrides_replace_the_sector_defaults():
    result = multiples.run(eps=10, ebitda=None, total_debt=0, cash=0,
                           shares_outstanding=100, sector="Technology", pe_override=5)
    assert result.pe_implied_price == pytest.approx(50.0)


def test_unknown_sector_uses_the_market_default():
    assert multiples.for_sector("Fictional") is multiples.DEFAULT_MULTIPLES
    assert multiples.for_sector(None) is multiples.DEFAULT_MULTIPLES


# ── verdict ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fair_value, expected", [
    (130, "BUY"), (100, "HOLD"), (110, "HOLD"), (80, "SELL"),
])
def test_margin_of_safety_defines_the_bands(fair_value, expected):
    verdict = decision.decide("X", current_price=100, dcf_value=fair_value,
                              multiples_value=fair_value)
    assert verdict.decision == expected


def test_blend_respects_the_dcf_weight():
    verdict = decision.decide("X", 100, dcf_value=100, multiples_value=200, dcf_weight=0.75)
    assert verdict.fair_value == pytest.approx(125.0)


def test_without_multiples_the_dcf_carries_the_verdict():
    verdict = decision.decide("X", 100, dcf_value=150, multiples_value=None)
    assert verdict.fair_value == pytest.approx(150.0)
    assert verdict.dcf_weight == 1.0
    assert verdict.multiples_weight == 0.0


def test_description_uses_the_instrument_currency():
    verdict = decision.decide("RELIANCE.NS", 1000, 1500, 1500, currency="INR")
    assert "₹" in verdict.describe()
    assert "undervalued" in verdict.describe()


# ── the pipeline ────────────────────────────────────────────────────────────

def test_default_assumptions_value_the_fixture_as_the_page_does(fundamentals):
    """AAPL at default assumptions: SELL, fair value $167.64 against $333.08."""
    result = analysis.value(fundamentals)
    assert result.verdict.decision == "SELL"
    assert result.verdict.fair_value == pytest.approx(167.64, abs=0.01)
    assert result.verdict.dcf_value == pytest.approx(133.42, abs=0.01)
    assert result.verdict.multiples_value == pytest.approx(218.97, abs=0.01)


def test_optimistic_assumptions_flip_the_verdict(fundamentals):
    optimistic = analysis.DEFAULTS.with_(growth_rate=0.35, wacc=0.07)
    assert analysis.value(fundamentals, optimistic).verdict.decision == "BUY"


def test_instruments_without_statements_are_refused_clearly():
    crypto = Fundamentals(symbol="BTC-USD", name="Bitcoin", currency="USD", price=60_000)
    with pytest.raises(MissingData, match="free cash flow"):
        analysis.value(crypto)
