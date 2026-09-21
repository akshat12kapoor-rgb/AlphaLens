"""Valuation: what a company is worth, by discounted cash flow and comparables."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from alphalens.charts import valuation as valuation_charts
from alphalens.core.currency import compact_money, money
from alphalens.data.models import MissingData
from alphalens.ui import context, layout
from alphalens.valuation import dcf
from alphalens.valuation.analysis import Assumptions, value

MODELS = {
    "Single stage": "One constant growth rate for 10 years, then terminal value.",
    "Two stage": "High growth for a few years, then terminal value.",
    "Three stage": "High growth, then a linear fade, then terminal value.",
}


def _assumptions(defaults: Assumptions, symbol: str) -> Assumptions:
    with st.sidebar:
        st.subheader("Assumptions")
        model = st.radio("DCF model", list(MODELS), index=1, key="val_model",
                         horizontal=True)
        st.caption(MODELS[model])

        growth = st.slider("Stage 1 FCF growth", 0, 40, int(defaults.growth_rate * 100),
                           format="%d%%", key="val_growth",
                           help="Annual free cash flow growth during the high-growth phase.")
        stage1 = 10 if model == "Single stage" else st.slider(
            "Stage 1 duration (years)", 1, 10, defaults.stage1_years, key="val_stage1")
        stage2 = st.slider("Stage 2 fade (years)", 1, 10, 5, key="val_stage2") \
            if model == "Three stage" else 0

        wacc = st.slider("Discount rate (WACC)", 5, 25, int(defaults.wacc * 100),
                         format="%d%%", key="val_wacc",
                         help="Your required return. Typically 8-12% for large caps.")
        terminal = st.slider("Terminal growth", 1, 5, int(defaults.terminal_growth * 100),
                             format="%d%%", key="val_terminal",
                             help="Long-run growth after the forecast, near GDP growth.")

        st.divider()
        st.subheader("Comparables")
        # Keyed by symbol: an override chosen for one ticker must not silently
        # carry into another ticker's fair-value calculation after switching.
        override = st.toggle("Override sector multiples", value=False,
                             key=f"val_override_{symbol}")
        pe = st.number_input("P/E", 1.0, 100.0, 20.0, 0.5, key=f"val_pe_{symbol}") \
            if override else None
        ev = st.number_input("EV/EBITDA", 1.0, 50.0, 12.0, 0.5, key=f"val_ev_{symbol}") \
            if override else None

        st.divider()
        weight = st.slider("DCF weight in the blend", 0, 100,
                           int(defaults.dcf_weight * 100), 5, format="%d%%", key="val_weight",
                           help="The rest is the comparables estimate.")

    return Assumptions(growth_rate=growth / 100, stage1_years=stage1, stage2_years=stage2,
                       wacc=wacc / 100, terminal_growth=terminal / 100,
                       dcf_weight=weight / 100, pe_override=pe, ev_ebitda_override=ev)


def render() -> None:
    symbol = context.ticker()
    layout.page_header("Valuation",
                       "What the business looks worth on its cash flows and on what the "
                       "market pays for similar companies.")

    loaded = context.attempt(context.fundamentals, symbol)
    if not loaded.ok:
        st.error(layout.markdown_safe(f"Could not load {symbol}: {loaded.error}"))
        return
    data = loaded.value
    assumptions = _assumptions(Assumptions(), symbol)

    try:
        result = value(data, assumptions)
    except MissingData as exc:
        st.warning(str(exc))
        st.caption("Instruments without published financial statements - crypto and most "
                   "ETFs - cannot be valued this way. The other AlphaLens tools still work.")
        return
    except ValueError as exc:
        st.error(str(exc))
        return

    verdict = result.verdict
    header, price, signal = st.columns([3, 1, 1])
    with header:
        st.markdown(f"### {data.name} `{data.symbol}`")
        st.caption(" · ".join(filter(None, [data.sector, data.industry])) or "—")
    layout.metric(price, "Market price", money(data.price, data.currency))
    layout.metric(signal, "Signal", verdict.label, f"{verdict.upside:+.1%} to fair value")

    st.caption(layout.markdown_safe(valuation_charts.summary_caption(result)))

    st.divider()
    left, right = st.columns([2, 3])
    with left:
        st.plotly_chart(valuation_charts.upside_gauge(result), width="stretch", key="val_gauge")
    with right:
        st.markdown(f"#### {verdict.describe()}")
        rows = [{"Method": name,
                 "Value per share": money(amount, verdict.currency),
                 "vs market": "—" if name == "Current Price"
                 else f"{amount / verdict.current_price - 1:+.1%}"}
                for name, amount in verdict.breakdown().items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", key="val_breakdown")
        overridden = assumptions.pe_override is not None
        st.caption(f"Multiples used: P/E {result.multiples.pe_multiple:.1f}× · "
                   f"EV/EBITDA {result.multiples.ev_ebitda_multiple:.1f}× · "
                   f"methods: {', '.join(result.multiples.methods) or 'none available'}"
                   + (" · **sector multiples overridden**" if overridden else ""))

    st.divider()
    st.subheader("Projections")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(valuation_charts.cash_flow_projection(result), width="stretch",
                        key="val_fcf")
        st.caption(f"Stage 1 present value {compact_money(result.dcf.stage1_pv, data.currency)} · "
                   f"terminal {compact_money(result.dcf.pv_terminal_value, data.currency)}")
    with right:
        revenues = dcf.project(data.revenue or 0, assumptions.growth_rate,
                               assumptions.terminal_growth, assumptions.stage1_years,
                               assumptions.stage2_years)
        st.plotly_chart(valuation_charts.revenue_projection(result, revenues),
                        width="stretch", key="val_revenue")

    st.plotly_chart(valuation_charts.value_comparison(result), width="stretch", key="val_compare")

    st.subheader("Sensitivity")
    st.caption("Intrinsic value per share across discount rate and stage 1 growth. "
               "Green is above today's price, red below.")
    grid = dcf.sensitivity(data.free_cash_flow, data.shares_outstanding,
                           assumptions.terminal_growth, assumptions.stage1_years,
                           assumptions.stage2_years)
    st.plotly_chart(valuation_charts.sensitivity(grid, verdict.current_price, data.currency),
                    width="stretch", key="val_sensitivity")

    st.caption("Educational use only — not financial advice.")
