"""One visual language for every chart in the platform."""
from __future__ import annotations

import plotly.graph_objects as go

BACKGROUND = "#0E1117"
PANEL = "#161B22"
GRID = "#1E2329"
TEXT = "#E6E9EF"
MUTED = "#8892A4"

UP = "#00C853"
DOWN = "#FF5252"
NEUTRAL = "#FFD600"
ACCENT = "#4A90E2"
GOLD = "#FFB020"
PURPLE = "#9B59B6"
ORANGE = "#FF8C00"

BULL_ZONE = "rgba(0, 200, 83, 0.10)"
BEAR_ZONE = "rgba(255, 82, 82, 0.10)"
BULL_EDGE = "rgba(0, 200, 83, 0.35)"
BEAR_EDGE = "rgba(255, 82, 82, 0.35)"

VERDICT_COLORS = {"BUY": UP, "HOLD": NEUTRAL, "SELL": DOWN}
SENTIMENT_COLORS = {"BULLISH": UP, "NEUTRAL": NEUTRAL, "BEARISH": DOWN}


def axes() -> dict:
    return dict(gridcolor=GRID, zerolinecolor="#333333", showgrid=True)


def apply(figure: go.Figure, height: int = 400, *, legend: bool = True,
          hover: str = "x unified") -> go.Figure:
    """The house style: transparent panels, muted grid, readable legend."""
    figure.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, family="Inter, system-ui, sans-serif"),
        margin=dict(l=48, r=24, t=32, b=24),
        showlegend=legend,
        hovermode=hover,
        hoverlabel=dict(bgcolor=PANEL, font_size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    bgcolor="rgba(14,17,23,0.6)", font=dict(size=11)),
    )
    figure.update_xaxes(**axes())
    figure.update_yaxes(**axes())
    for annotation in figure.layout.annotations:
        annotation.font.color = MUTED
        annotation.font.size = 11
    return figure


def money_hover(currency_symbol: str, decimals: int = 2) -> str:
    return f"{currency_symbol}%{{y:,.{decimals}f}}<extra></extra>"


def empty(message: str = "No data") -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        annotations=[dict(text=message, showarrow=False, font=dict(size=16, color=MUTED))],
        xaxis=dict(visible=False), yaxis=dict(visible=False))
    return apply(figure, height=220, legend=False)
