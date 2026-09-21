"""
Caching that works with or without Streamlit.

The data layer is imported by the CLIs and the tests as well as the app, so it
can't depend on a Streamlit session. Inside the app this delegates to
`st.cache_data` (a process-wide cache shared across sessions, cleared by
Streamlit); outside it falls back to an unbounded process-level memo.
"""
from __future__ import annotations

import functools
import time
from typing import Callable, TypeVar

from alphalens.core.config import CACHE_TTL

F = TypeVar("F", bound=Callable)


def cached(ttl: int = CACHE_TTL, spinner: str | bool = True) -> Callable[[F], F]:
    """Cache a data call for `ttl` seconds.

    Which cache is used is decided per call, not at import: the same function is
    imported by the app, the CLIs and the tests, and only the app has a
    Streamlit runtime to cache in. Calling st.cache_data outside one works but
    warns on every call.

    `spinner` is forwarded to `st.cache_data` so a live (uncached) fetch is
    visible rather than looking like a frozen app - pass a message describing
    what's being fetched, or False to suppress it.
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

                    streamlit_cached = st.cache_data(ttl=ttl, show_spinner=spinner)(fn)
                return streamlit_cached(*args, **kwargs)
            return memo(*args, **kwargs)

        wrapper.clear = getattr(memo, "cache_clear", lambda: None)
        return wrapper  # type: ignore[return-value]

    return decorate


#: Failures recorded by `negative_cache`, keyed by (function name, args, kwargs).
_FAILURES: dict[tuple, tuple[float, BaseException]] = {}


def negative_cache(ttl: int = 30) -> Callable[[F], F]:
    """Cache a call's *failure* for `ttl` seconds.

    `st.cache_data` (used by `cached()`) never caches an exception, so a
    failing call is retried on every single Streamlit rerun - any widget
    interaction, not just a manual refresh. During a real outage or rate
    limit, that turns each open session into a stream of retries against an
    already-struggling endpoint. Put this outside `cached()`: a call inside
    the cooldown window never reaches the cached function, let alone the
    network.
    """
    def decorate(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (fn.__name__, args, tuple(sorted(kwargs.items())))
            failure = _FAILURES.get(key)
            if failure is not None:
                expires_at, exc = failure
                if time.monotonic() < expires_at:
                    raise exc
                del _FAILURES[key]
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - cache whatever fn raises
                _FAILURES[key] = (time.monotonic() + ttl, exc)
                raise

        wrapper.clear_failures = lambda: _FAILURES.clear()
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
