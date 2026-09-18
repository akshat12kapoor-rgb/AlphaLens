"""Charts for the sentiment page."""
from __future__ import annotations

import plotly.graph_objects as go

from alphalens.charts import theme


def ticker_scores(labels: list[str], scores: list[float], sentiments: list[str]) -> go.Figure:
    """Mean tone per ticker on the -1 to +1 scale."""
    figure = go.Figure(go.Bar(
        x=scores, y=labels, orientation="h",
        marker_color=[theme.SENTIMENT_COLORS[s] for s in sentiments],
        text=[f"{value:+.3f}" for value in scores], textposition="outside",
        hovertemplate="%{y}: %{x:+.3f}<extra></extra>"))
    figure.update_xaxes(range=[-1, 1], zeroline=True, zerolinecolor=theme.MUTED)
    figure.update_yaxes(autorange="reversed")
    return theme.apply(figure, height=60 + 45 * max(len(labels), 1), legend=False,
                       hover="closest")


def daily_tone(days: list[str], values: list[float], sentiment: str) -> go.Figure:
    """How the tone moved day by day."""
    figure = go.Figure(go.Scatter(
        x=days, y=values, mode="lines+markers",
        line=dict(color=theme.SENTIMENT_COLORS[sentiment], width=2),
        hovertemplate="%{x}: %{y:+.3f}<extra></extra>"))
    figure.add_hline(y=0, line_color=theme.MUTED, line_dash="dot")
    figure.update_yaxes(range=[-1.05, 1.05], title_text="daily tone")
    figure.update_xaxes(type="category")
    return theme.apply(figure, height=260, legend=False)
