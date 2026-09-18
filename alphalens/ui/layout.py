"""Small Streamlit helpers shared by the pages."""
from __future__ import annotations

import streamlit as st


def markdown_safe(text: str) -> str:
    """Escape `$` for Streamlit markdown.

    A pair of dollar signs opens a LaTeX span, so "fair value $167 · price $333"
    renders as a garbled formula. Metric *values* are not markdown and need no
    escaping; captions, markdown and metric deltas do.
    """
    return text.replace("$", "\\$")


def page_header(title: str, caption: str = "") -> None:
    st.title(title)
    if caption:
        st.caption(caption)


def unavailable(attempt, what: str = "") -> None:
    """Explain a failed data call where the content would have gone."""
    prefix = f"{what}: " if what else ""
    st.caption(markdown_safe(f"{prefix}unavailable — {attempt.error}"))


def metric(container, label: str, value: str, delta: str | None = None, **kwargs) -> None:
    """A metric whose delta is markdown-safe."""
    container.metric(label, value, markdown_safe(delta) if delta else None, **kwargs)


def strategy_help(strategy) -> None:
    """The expandable explanation shown next to a strategy choice."""
    with st.expander(f"How {strategy.name} works"):
        st.markdown(strategy.explanation)
        if strategy.parameters:
            st.caption("Parameters: " + ", ".join(p.label for p in strategy.parameters))
