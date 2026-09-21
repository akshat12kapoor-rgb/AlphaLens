"""The replay session's chart-window bookkeeping. No Streamlit runtime needed:
`Session` is a plain dataclass, and `visible`/`visible_start` are pure
computations over its `frame`/`index` fields."""
import pandas as pd

from alphalens.ui import replay


def session_at(index: int, length: int = 400) -> replay.Session:
    state = replay.Session()
    state.frame = pd.DataFrame({"close": range(length)})
    state.index = index
    return state


def test_visible_is_capped_at_chart_window_once_the_replay_has_run_long_enough():
    state = session_at(replay.CHART_WINDOW + 149)
    assert len(state.visible) == replay.CHART_WINDOW
    assert state.visible_start == 150


def test_visible_is_the_full_prefix_before_the_window_fills_up():
    state = session_at(10)
    assert len(state.visible) == 11
    assert state.visible_start == 0


def test_visible_always_ends_on_the_current_bar():
    state = session_at(replay.CHART_WINDOW + 149)
    assert state.visible.iloc[-1]["close"] == state.frame.iloc[state.index]["close"]


def gaps_at(*start_idx: int) -> pd.DataFrame:
    return pd.DataFrame({"start_idx": list(start_idx), "type": ["bullish"] * len(start_idx),
                         "top": [1.0] * len(start_idx), "bottom": [0.0] * len(start_idx)})


def test_windowed_gaps_is_a_no_op_with_no_offset():
    gaps = gaps_at(5, 200)
    assert replay.windowed_gaps(gaps, 0) is gaps


def test_windowed_gaps_drops_gaps_that_start_before_the_window():
    gaps = gaps_at(5, 200, 260)
    result = replay.windowed_gaps(gaps, 150)
    assert list(result["start_idx"]) == [50, 110]  # 200-150, 260-150; 5 fell out of the window


def test_windowed_gaps_passes_through_none_and_empty():
    assert replay.windowed_gaps(None, 150) is None
    empty = gaps_at()
    assert replay.windowed_gaps(empty, 150) is empty
