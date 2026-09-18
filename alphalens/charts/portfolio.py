"""Equity, drawdown and position charts, for both the simulator and backtests."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from alphalens.backtest.engine import BacktestResult
from alphalens.charts import theme
from alphalens.core.currency import symbol_for


def equity_curve(history: list[tuple], initial_capital: float,
                 currency: str = "USD") -> go.Figure:
    """The simulator's running portfolio value."""
    if not history:
        return theme.empty("No trades yet")

    unit = symbol_for(currency)
    times = [point[0] for point in history]
    values = [point[1] for point in history]
    gained = values[-1] >= values[0]

    figure = go.Figure(go.Scatter(
        x=times, y=values, mode="lines", name="Portfolio",
        line=dict(color=theme.UP if gained else theme.DOWN, width=2),
        fill="tozeroy",
        fillcolor="rgba(0,200,83,0.08)" if gained else "rgba(255,82,82,0.08)",
        hovertemplate=theme.money_hover(unit, 0)))
    figure.add_hline(y=initial_capital, line_dash="dash", line_color=theme.MUTED,
                     annotation_text=" starting capital", annotation_font_color=theme.MUTED)
    return theme.apply(figure, height=300, legend=False)


def backtest_result(result: BacktestResult, benchmark: BacktestResult) -> go.Figure:
    """Strategy against buy and hold, with both drawdowns underneath."""
    unit = symbol_for(result.currency)
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28],
                           vertical_spacing=0.05)

    figure.add_trace(go.Scatter(x=benchmark.dates, y=benchmark.equity, name="Buy & hold",
                                line=dict(color=theme.MUTED, width=1.5),
                                hovertemplate=theme.money_hover(unit, 0)), row=1, col=1)
    figure.add_trace(go.Scatter(x=result.dates, y=result.equity, name=result.strategy,
                                line=dict(color=theme.ACCENT, width=2.2),
                                hovertemplate=theme.money_hover(unit, 0)), row=1, col=1)

    figure.add_trace(go.Scatter(x=result.dates, y=result.drawdown_series, name="Drawdown",
                                line=dict(color=theme.ACCENT, width=1), fill="tozeroy",
                                fillcolor="rgba(74,144,226,0.15)", showlegend=False),
                     row=2, col=1)
    figure.add_trace(go.Scatter(x=benchmark.dates, y=benchmark.drawdown_series,
                                name="Benchmark drawdown", line=dict(color=theme.MUTED, width=1),
                                showlegend=False), row=2, col=1)

    figure.update_yaxes(title_text=f"equity ({unit})", row=1, col=1)
    figure.update_yaxes(title_text="drawdown", tickformat=".0%", row=2, col=1)
    return theme.apply(figure, height=480)


def positions(frame: pd.DataFrame, held: list[float], currency: str = "USD") -> go.Figure:
    """Price with a marker wherever the target position changed."""
    unit = symbol_for(currency)
    figure = go.Figure(go.Scatter(x=frame.index, y=frame["close"], name="Close",
                                  line=dict(color=theme.TEXT, width=1.3),
                                  hovertemplate=theme.money_hover(unit)))
    changes = {"long": ([], []), "short": ([], []), "flat": ([], [])}
    previous = 0.0
    for when, price, position in zip(frame.index, frame["close"], held):
        if position != previous:
            side = "long" if position > 0 else "short" if position < 0 else "flat"
            changes[side][0].append(when)
            changes[side][1].append(price)
        previous = position

    for side, marker, color in (("long", "triangle-up", theme.UP),
                                ("short", "triangle-down", theme.DOWN),
                                ("flat", "x", theme.MUTED)):
        times, prices = changes[side]
        if times:
            figure.add_trace(go.Scatter(x=times, y=prices, mode="markers", name=f"→ {side}",
                                        marker=dict(symbol=marker, size=10, color=color),
                                        hovertemplate=f"→ {side} @ {unit}%{{y:,.2f}}<extra></extra>"))
    figure.update_yaxes(title_text=f"price ({unit})")
    return theme.apply(figure, height=360)


def sweep_heatmap(grid: pd.DataFrame, x: str, y: str, value: str = "sharpe") -> go.Figure:
    """A parameter sweep as a grid of outcomes."""
    if grid.empty:
        return theme.empty("No valid combinations")
    table = grid.pivot(index=y, columns=x, values=value)
    figure = go.Figure(go.Heatmap(
        z=table.values, x=[str(c) for c in table.columns], y=[str(i) for i in table.index],
        colorscale="RdYlGn", zmid=0, text=table.round(2).values, texttemplate="%{text}",
        colorbar=dict(title=value.title())))
    figure.update_xaxes(title_text=x)
    figure.update_yaxes(title_text=y)
    return theme.apply(figure, height=320, legend=False, hover="closest")
