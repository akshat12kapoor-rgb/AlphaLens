"""The simulator page's ticker status line: pure text logic, no Streamlit
runtime needed."""
import pandas as pd

from alphalens.ui import replay
from alphalens.ui.pages.simulator import _replay_status


def session(loaded_symbol: str | None) -> replay.Session:
    state = replay.Session()
    if loaded_symbol is not None:
        state.frame = pd.DataFrame({"close": [1.0, 2.0]})
        state.symbol = loaded_symbol
    return state


def test_status_before_anything_is_loaded():
    line = _replay_status(session(None), "AAPL")
    assert "Not loaded yet" in line
    assert "**AAPL**" in line


def test_status_when_loaded_ticker_matches_the_active_one():
    line = _replay_status(session("AAPL"), "AAPL")
    assert line == "Simulating **AAPL**"


def test_status_when_loaded_ticker_is_stale():
    line = _replay_status(session("AAPL"), "MSFT")
    assert line == "⚠️ Showing **AAPL**. Load data to switch to **MSFT**."


def test_status_is_a_single_line_not_two_stacked_captions():
    """The bug this replaces: an unconditional 'Simulating X' caption stacked
    with a separate 'Showing Y' warning when X != Y - two claims on screen at
    once. `_replay_status` returns one string, so that can't happen again."""
    line = _replay_status(session("AAPL"), "MSFT")
    assert isinstance(line, str) and "\n" not in line
