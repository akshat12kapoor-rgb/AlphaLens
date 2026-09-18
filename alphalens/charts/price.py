"""Candlestick charts: overlays, indicator panels, smart-money zones, trades."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from alphalens.charts import theme
from alphalens.core.currency import symbol_for

#: Keep the chart readable rather than burying it in history.
MAX_ZONES = 6
ZONE_EXTEND = 20
MAX_SWEEPS = 15


def unfilled_gaps(gaps: pd.DataFrame, frame: pd.DataFrame, limit: int = MAX_ZONES) -> pd.DataFrame:
    """The most recent gaps price has not traded back into.

    A gap that has been filled is no longer actionable, and showing every
    historical one makes the chart unreadable.
    """
    if gaps is None or gaps.empty:
        return gaps
    highs, lows = frame["high"].values, frame["low"].values
    active = []
    for _, gap in gaps.iterrows():
        start = int(gap["start_idx"])
        later = zip(highs[start + 2:], lows[start + 2:])
        if not any(low <= gap["top"] and high >= gap["bottom"] for high, low in later):
            active.append(gap)
    return pd.DataFrame(active).tail(limit) if active else gaps.tail(limit)


def candles(frame: pd.DataFrame, *, currency: str = "USD", title: str = "",
            signals: pd.Series | None = None, gaps: pd.DataFrame | None = None,
            sweeps: pd.DataFrame | None = None, trades: list | None = None,
            show_ma: bool = True, show_rsi: bool = True, show_macd: bool = False,
            show_gaps: bool = False, show_sweeps: bool = False,
            show_signals: bool = False, show_trades: bool = True,
            current_index: int | None = None, height: int = 620) -> go.Figure:
    """The simulator's main chart, and the price view anywhere else."""
    if frame.empty:
        return theme.empty("No price data")

    unit = symbol_for(currency)
    rows = [0.70] + ([0.18] if show_rsi else []) + ([0.18] if show_macd else [])
    titles = [title] + (["RSI (14)"] if show_rsi else []) + (["MACD (12, 26, 9)"] if show_macd else [])
    rsi_row = 2 if show_rsi else None
    macd_row = (3 if show_rsi else 2) if show_macd else None

    figure = make_subplots(rows=len(rows), cols=1, shared_xaxes=True,
                           row_heights=rows, vertical_spacing=0.045,
                           subplot_titles=titles)

    figure.add_trace(go.Candlestick(
        x=frame.index, open=frame["open"], high=frame["high"], low=frame["low"],
        close=frame["close"], name="Price",
        increasing=dict(line_color=theme.UP, fillcolor=theme.UP),
        decreasing=dict(line_color=theme.DOWN, fillcolor=theme.DOWN)), row=1, col=1)

    if show_ma:
        for column, color, dash in (("sma_20", theme.GOLD, None), ("sma_50", theme.ORANGE, None),
                                    ("ema_20", theme.ACCENT, "dash")):
            if column in frame:
                figure.add_trace(go.Scatter(
                    x=frame.index, y=frame[column], name=column.replace("_", " ").upper(),
                    line=dict(color=color, width=1.4, dash=dash),
                    hovertemplate=theme.money_hover(unit)), row=1, col=1)

    if show_gaps and gaps is not None and not gaps.empty:
        _draw_gaps(figure, unfilled_gaps(gaps, frame), frame)
    if show_sweeps and sweeps is not None and not sweeps.empty:
        _draw_sweeps(figure, sweeps.tail(MAX_SWEEPS), unit)
    if show_signals and signals is not None:
        _draw_signals(figure, frame, signals, unit)
    if show_trades and trades:
        _draw_trades(figure, trades, unit)

    if current_index is not None and 0 <= current_index < len(frame):
        figure.add_vline(x=frame.index[current_index], line_width=1,
                         line_dash="dot", line_color=theme.MUTED, opacity=0.6)

    if rsi_row and "rsi" in frame:
        figure.add_trace(go.Scatter(x=frame.index, y=frame["rsi"], name="RSI",
                                    line=dict(color=theme.PURPLE, width=1.5),
                                    fill="tozeroy", fillcolor="rgba(155,89,182,0.06)"),
                         row=rsi_row, col=1)
        for level, color in ((70, theme.DOWN), (50, "#555555"), (30, theme.UP)):
            figure.add_hline(y=level, line_dash="dash", line_color=color, line_width=0.7,
                             opacity=0.6, row=rsi_row, col=1)
        figure.update_yaxes(range=[0, 100], row=rsi_row, col=1)

    if macd_row and "macd" in frame:
        colors = [theme.UP if v >= 0 else theme.DOWN for v in frame["macd_diff"].fillna(0)]
        figure.add_trace(go.Bar(x=frame.index, y=frame["macd_diff"], name="Histogram",
                                marker_color=colors, opacity=0.65), row=macd_row, col=1)
        figure.add_trace(go.Scatter(x=frame.index, y=frame["macd"], name="MACD",
                                    line=dict(color=theme.ACCENT, width=1.4)), row=macd_row, col=1)
        figure.add_trace(go.Scatter(x=frame.index, y=frame["macd_signal"], name="Signal",
                                    line=dict(color=theme.ORANGE, width=1.4)), row=macd_row, col=1)

    figure.update_layout(xaxis_rangeslider_visible=False)
    return theme.apply(figure, height=height)


def event_chart(frame: pd.DataFrame, event: dict, *, currency: str = "USD",
                window: int = 30) -> go.Figure:
    """A zoomed view of the bars around one signal, for Learning Mode."""
    index = min(event.get("index", len(frame) - 1), len(frame) - 1)
    start = max(0, index - window + 1)
    focus = frame.iloc[start:index + 1]
    if focus.empty:
        return theme.empty("No candles to show")

    unit = symbol_for(currency)
    figure = go.Figure(go.Candlestick(
        x=focus.index, open=focus["open"], high=focus["high"], low=focus["low"],
        close=focus["close"], name="Price",
        increasing=dict(line_color=theme.UP, fillcolor=theme.UP),
        decreasing=dict(line_color=theme.DOWN, fillcolor=theme.DOWN)))

    if "sma_20" in focus:
        figure.add_trace(go.Scatter(x=focus.index, y=focus["sma_20"], name="SMA 20",
                                    line=dict(color=theme.GOLD, width=1.2)))

    kind = event.get("kind", "signal")
    price = float(event.get("price", focus["close"].iloc[-1]))
    figure.add_annotation(x=focus.index[-1], y=price, text=f"<b>{event.get('label', kind)}</b>",
                          showarrow=True, arrowhead=2, arrowcolor=theme.GOLD,
                          bgcolor=theme.PANEL, bordercolor=theme.GOLD,
                          font=dict(color=theme.TEXT, size=11), ay=-40)

    if kind == "fvg" and {"top", "bottom"} <= event.keys():
        figure.add_hrect(y0=event["bottom"], y1=event["top"],
                         fillcolor=theme.BULL_ZONE if event.get("direction") == "bullish"
                         else theme.BEAR_ZONE, line_width=0)
        # Mark the three candles that formed the gap.
        for offset, label in ((-2, "C1"), (-1, "C2"), (0, "C3")):
            position = len(focus) - 1 + offset
            if 0 <= position < len(focus):
                figure.add_annotation(x=focus.index[position], y=focus["low"].iloc[position],
                                      text=label, showarrow=False, yshift=-16,
                                      font=dict(color=theme.MUTED, size=10))
    if kind == "sweep" and "swept_level" in event:
        figure.add_hline(y=event["swept_level"], line_dash="dot", line_color=theme.PURPLE,
                         annotation_text=f" swept {unit}{event['swept_level']:,.2f}",
                         annotation_font_color=theme.MUTED)

    figure.update_layout(xaxis_rangeslider_visible=False)
    return theme.apply(figure, height=320, legend=False)


def _draw_gaps(figure: go.Figure, gaps: pd.DataFrame, frame: pd.DataFrame) -> None:
    for _, gap in gaps.iterrows():
        start = int(gap["start_idx"])
        end = min(start + ZONE_EXTEND, len(frame) - 1)
        bullish = gap["type"] == "bullish"
        figure.add_shape(type="rect", x0=frame.index[start], x1=frame.index[end],
                         y0=gap["bottom"], y1=gap["top"],
                         fillcolor=theme.BULL_ZONE if bullish else theme.BEAR_ZONE,
                         line=dict(color=theme.BULL_EDGE if bullish else theme.BEAR_EDGE,
                                   width=1), layer="below", row=1, col=1)


def _draw_sweeps(figure: go.Figure, sweeps: pd.DataFrame, unit: str) -> None:
    for kind, marker, color in (("buy_side", "triangle-down", theme.DOWN),
                                ("sell_side", "triangle-up", theme.UP)):
        rows = sweeps[sweeps["type"] == kind]
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["index"], y=rows["wick_price"], mode="markers",
            name=f"{kind.replace('_', ' ')} sweep",
            marker=dict(symbol=marker, size=11, color=color, line=dict(width=1, color="#000")),
            hovertemplate=(f"{kind.replace('_', ' ')} sweep<br>wick {unit}%{{y:,.2f}}"
                           "<extra></extra>")), row=1, col=1)


def _draw_signals(figure: go.Figure, frame: pd.DataFrame, signals: pd.Series, unit: str) -> None:
    for label, marker, color, price_column in (("BUY", "triangle-up", theme.UP, "low"),
                                               ("SELL", "triangle-down", theme.DOWN, "high")):
        mask = signals == label
        if not mask.any():
            continue
        figure.add_trace(go.Scatter(
            x=frame.index[mask], y=frame[price_column][mask], mode="markers",
            name=f"{label} signal",
            marker=dict(symbol=marker, size=9, color=color, opacity=0.65),
            hovertemplate=f"{label} signal @ {unit}%{{y:,.2f}}<extra></extra>"), row=1, col=1)


def _draw_trades(figure: go.Figure, trades: list, unit: str) -> None:
    colors = {"BUY": theme.UP, "COVER": theme.UP, "SELL": theme.DOWN, "SHORT": theme.DOWN}
    for action in ("BUY", "COVER", "SELL", "SHORT"):
        rows = [t for t in trades if t.action == action]
        if not rows:
            continue
        figure.add_trace(go.Scatter(
            x=[t.timestamp for t in rows], y=[t.price for t in rows], mode="markers",
            name=action, marker=dict(size=9, color=colors[action],
                                     line=dict(width=1.5, color="#0E1117")),
            customdata=[[t.quantity] for t in rows],
            hovertemplate=(f"<b>{action}</b> %{{customdata[0]}} @ {unit}%{{y:,.2f}}"
                           "<extra></extra>")), row=1, col=1)
