"""Charts for the valuation page: projections, comparison, sensitivity, upside."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from alphalens.charts import theme
from alphalens.core.currency import compact_money, symbol_for
from alphalens.valuation.analysis import Valuation


def cash_flow_projection(result: Valuation) -> go.Figure:
    """Projected free cash flow and what each year is worth today."""
    dcf = result.dcf
    unit = symbol_for(result.fundamentals.currency)
    years = dcf.year_labels

    figure = go.Figure()
    figure.add_trace(go.Bar(x=years, y=dcf.projected_fcf, name="Projected FCF",
                            marker_color=theme.ACCENT, opacity=0.55,
                            hovertemplate=theme.money_hover(unit, 0)))
    figure.add_trace(go.Bar(x=years, y=dcf.present_values, name="Present value",
                            marker_color=theme.UP,
                            hovertemplate=theme.money_hover(unit, 0)))
    if dcf.stage2_years:
        figure.add_vline(x=dcf.stage1_years - 0.5, line_dash="dot", line_color=theme.MUTED,
                         annotation_text=" fade begins", annotation_font_color=theme.MUTED)
    figure.update_layout(barmode="overlay")
    figure.update_yaxes(title_text=f"free cash flow ({unit})")
    return theme.apply(figure, height=340)


def revenue_projection(result: Valuation, revenues: list[float]) -> go.Figure:
    """History against the same growth path the DCF assumes."""
    history = result.fundamentals.revenue_history
    unit = symbol_for(result.fundamentals.currency)
    figure = go.Figure()
    if not history.empty:
        figure.add_trace(go.Bar(x=list(history.index), y=list(history.values), name="Reported",
                                marker_color=theme.MUTED,
                                hovertemplate=theme.money_hover(unit, 0)))
    labels = [f"+{i}y" for i in range(1, len(revenues) + 1)]
    figure.add_trace(go.Bar(x=labels, y=revenues, name="Projected", marker_color=theme.ACCENT,
                            hovertemplate=theme.money_hover(unit, 0)))
    figure.update_yaxes(title_text=f"revenue ({unit})")
    return theme.apply(figure, height=320)


def value_comparison(result: Valuation) -> go.Figure:
    """Each method's value per share against the market price."""
    verdict = result.verdict
    unit = symbol_for(verdict.currency)
    rows = verdict.breakdown()
    colors = [theme.MUTED if name == "Current Price"
              else theme.UP if value >= verdict.current_price else theme.DOWN
              for name, value in rows.items()]
    figure = go.Figure(go.Bar(
        x=list(rows), y=list(rows.values()), marker_color=colors,
        text=[f"{unit}{v:,.2f}" for v in rows.values()], textposition="outside",
        hovertemplate=theme.money_hover(unit)))
    figure.add_hline(y=verdict.current_price, line_dash="dash", line_color=theme.MUTED,
                     annotation_text=" market price", annotation_font_color=theme.MUTED)
    figure.update_yaxes(title_text=f"value per share ({unit})")
    return theme.apply(figure, height=340, legend=False)


def sensitivity(grid: pd.DataFrame, current_price: float, currency: str) -> go.Figure:
    """Intrinsic value across discount rate and growth, against today's price."""
    unit = symbol_for(currency)
    figure = go.Figure(go.Heatmap(
        z=grid.values, x=list(grid.columns), y=list(grid.index), colorscale="RdYlGn",
        zmid=current_price, text=grid.values, texttemplate="%{text:,.0f}",
        colorbar=dict(title=f"value ({unit})"),
        hovertemplate=("growth %{x} · WACC %{y}<br>" + unit + "%{z:,.2f}<extra></extra>")))
    figure.update_xaxes(title_text="stage 1 growth")
    figure.update_yaxes(title_text="discount rate (WACC)")
    return theme.apply(figure, height=360, legend=False, hover="closest")


def upside_gauge(result: Valuation) -> go.Figure:
    """How far the blended fair value sits from the market price."""
    verdict = result.verdict
    upside = verdict.upside * 100
    figure = go.Figure(go.Indicator(
        mode="gauge+number", value=upside,
        number={"suffix": "%", "font": {"color": verdict.color, "size": 34}},
        title={"text": f"{verdict.symbol} upside to fair value", "font": {"size": 13}},
        gauge={
            "axis": {"range": [-60, 60], "tickwidth": 1, "tickcolor": theme.MUTED},
            "bar": {"color": verdict.color, "thickness": 0.7},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [-60, -15], "color": "rgba(255,82,82,0.18)"},
                {"range": [-15, 15], "color": "rgba(255,214,0,0.15)"},
                {"range": [15, 60], "color": "rgba(0,200,83,0.18)"},
            ],
            "threshold": {"line": {"color": theme.TEXT, "width": 2}, "value": 0},
        }))
    return theme.apply(figure, height=260, legend=False, hover="closest")


def summary_caption(result: Valuation) -> str:
    data = result.fundamentals
    return (f"Revenue {compact_money(data.revenue, data.currency)} · "
            f"FCF {compact_money(data.free_cash_flow, data.currency)} · "
            f"EBITDA {compact_money(data.ebitda, data.currency)}")
