"""
Caching that works with or without Streamlit.

The data layer is imported by the CLIs and the tests as well as the app, so it
can't depend on a Streamlit session. Inside the app this delegates to
`st.cache_data` (per-session TTL, cleared by Streamlit); outside it falls back
to an unbounded process-level memo.
"""
from __future__ import annotations

import functools
from typing import Callable, TypeVar

from alphalens.core.config import CACHE_TTL

F = TypeVar("F", bound=Callable)


def cached(ttl: int = CACHE_TTL) -> Callable[[F], F]:
    """Cache a data call for `ttl` seconds.

    Which cache is used is decided per call, not at import: the same function is
    imported by the app, the CLIs and the tests, and only the app has a
    Streamlit runtime to cache in. Calling st.cache_data outside one works but
    warns on every call.
    """
    def decorate(fn: F) -> F:
        memo = functools.lru_cache(maxsize=64)(fn)
        streamlit_cached = None

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            nonlocal streamlit_cached
            if _streamlit_running():
                if streamlit_cached is None:
                    import streamlit as st

                    streamlit_cached = st.cache_data(ttl=ttl, show_spinner=False)(fn)
                return streamlit_cached(*args, **kwargs)
            return memo(*args, **kwargs)

        wrapper.clear = getattr(memo, "cache_clear", lambda: None)
        return wrapper  # type: ignore[return-value]

    return decorate


def _streamlit_running() -> bool:
    try:
        from streamlit.runtime import exists
    except ModuleNotFoundError:
        return False
    try:
        return bool(exists())
    except Exception:  # noqa: BLE001 - never let caching break a data call
        return False
