# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Platform shape

AlphaLens is **one platform with three surfaces**, not three products. They share
a theme (retail-investor tooling on yfinance + Streamlit) and a convention: a
`modules/` package of pure, Streamlit-free functions behind a single `app.py`.

| Directory | Surface | What it does |
|---|---|---|
| `stock_simulator/` | Simulator (`TradingSimTALP`) | Candle-by-candle replay + paper trading |
| `stock-valuation-dashboard/` | Valuation | DCF + comparable-multiples dashboard |
| `SentimentFinance/` | Sentiment | Stdlib CLI scoring financial headlines |

Two mechanical facts that follow from how it's laid out:

- **Each surface is its own git repo with its own remote**, and the root is a
  fourth repo that tracks only platform-level files (`CLAUDE.md`, `.claude/`).
  Run git with `-C <surface>` for surface changes, and expect them to land in
  that surface's history, not a platform-wide commit. The root `.gitignore`
  excludes all three surface directories on purpose: `git add` on a directory
  containing a `.git` records a **gitlink** (mode 160000), a broken submodule
  pointer whose contents are not tracked. If you ever want them genuinely linked,
  register them as real submodules (`git submodule add <remote> <dir>` after
  un-ignoring) rather than letting them be added accidentally.
- **`stock_simulator/` and `stock-valuation-dashboard/` both ship a top-level
  package named `modules`.** Only one can be imported per Python process —
  whichever is first on `sys.path` wins, and the other's imports fail with a
  misleading `ModuleNotFoundError: No module named 'modules.trading_engine'`.
  Never import from both in one interpreter; run one surface per process.

## Running it

There is a run skill at `.claude/skills/run-alphalens/` — **start there**, it is
verified end-to-end and drives all three surfaces headlessly against committed
offline fixtures:

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py all
```

One shared venv at the root serves the whole platform (the two Streamlit apps'
requirements are compatible; the sentiment CLI is stdlib-only). See the skill for
setup, screenshots (`shot.py`), live-server mode (`serve.py`), and gotchas.

For quick module-level work without Streamlit:

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py engine
```

## Commands

The sentiment CLI needs no venv:

```bash
cd SentimentFinance && python3 analyze.py data/headlines.txt --verbose
```

Its unit tests are the only test suite in the platform:

```bash
cd SentimentFinance && python3 -m unittest discover -s tests -t .
```

Run a single test: `python3 -m unittest tests.test_sentiment.TestScoreText.test_negation -v`

The two Streamlit surfaces have **no test suite and no linter config** — the run
skill's `driver.py sim` / `driver.py val` are their regression check, and they
assert rather than just print. Verify `modules/` changes by importing them
directly, which works because those modules are deliberately Streamlit-free.

`requirements.txt` files set only floors, so a fresh install today resolves to
pandas 3.0 / numpy 2.5 / streamlit 1.63 / plotly 7.0 — much newer than the code
was written against. It works, but `stock-valuation-dashboard/app.py` still calls
`use_container_width=`, which Streamlit reports as removed after 2025-12-31 and
currently only warns about. `stock_simulator` already migrated to `width="stretch"`.

## stock-valuation-dashboard — architecture

One-shot pipeline, re-run top-to-bottom on every Streamlit rerun (`app.py:300-380`):

```
fetch_stock_data(ticker)      → flat dict of ~15 normalised metrics
  ├→ run_dcf(...)             → intrinsic value per share
  ├→ run_multiples_valuation(...) → P/E + EV/EBITDA implied prices
  └→ make_decision(...)       → ValuationResult (BUY/HOLD/SELL)
        → charts.* build Plotly figures from those dicts
```

Things that are easy to get wrong here:

- **`data_fetcher.fetch_stock_data` is the only yfinance boundary.** It flattens
  three statements plus `info` into one dict and tolerates missing fields by
  returning `None` (`_safe_get`, `_latest`, `_extract_series` try several possible
  Yahoo row names). Downstream models must keep handling `None` for `eps`,
  `ebitda`, and `multiples_value` — a ticker with no earnings is a normal case,
  not an error.
- **The DCF is two-stage (5 high-growth + 5 fade years), not the single 5-year
  model the README describes.** `run_dcf` returns `growth_rates_used` so charts can
  show the fade. Trust the code over the README here.
- `_validate_inputs` enforces `wacc > terminal_growth`; the Gordon Growth terminal
  value explodes otherwise. Slider ranges in `app.py` exist to uphold that.
- `MARGIN_OF_SAFETY = 0.15` in `decision_engine.py` is the single source of the
  BUY/HOLD/SELL bands; `DECISION_CONFIG` carries the emoji/colour per verdict.
  Add a verdict in both places or the UI breaks.
- `multiples_model.SECTOR_MULTIPLES` is a hardcoded sector→multiple table with an
  `"N/A"` fallback row. Sector strings come verbatim from yfinance `info["sector"]`.

## stock_simulator — architecture

Fetch-once, then replay a growing slice of the same DataFrame:

```
fetch_data()                 → lowercase OHLCV DataFrame, tz-stripped, volume>0
  → calculate_all_indicators() → returns a COPY with sma_20/sma_50/ema_20/rsi/macd* columns
  → get_smc_analysis()         → fvg_df + sweeps_df, computed once upfront
  → get_signals(df, strategy)  → per-bar "BUY"/"SELL"/"HOLD" Series
  → replay loop advances replay_idx; chart_renderer renders df.iloc[:idx]
```

- **Column names are lowercase** (`open/high/low/close/volume`) — `data_fetcher`
  renames them. Indicator columns are f-string-built (`sma_{window}`), so changing
  a default window silently renames a column every other module reads.
- `indicators.py` prefers the `ta` package but falls back to hand-rolled pandas
  implementations if the import fails — keep both branches in sync when editing.
- **`TradingEngine` uses one signed `holdings` integer**: `>0` long, `<0` short,
  `0` flat, with `avg_entry_price` tracking whichever side is active. `buy()`
  covers any short before opening a long and `sell()` closes any long before
  opening a short; a flip appends **two** `Trade` records. Any change to P&L must
  work for both signs of `holdings` — there is deliberately one formula, not two.
  Short margin is a 100% cash-collateral proxy against `balance`.
- **The replay loop is an `st.fragment(run_every=0.25)` declared at module level**
  (`app.py:337`) so its identity is stable across reruns; it reads everything from
  `st.session_state` and captures nothing. It calls `st.rerun(scope="app")` to
  escape the fragment when data ends or Learning Mode pauses. Do not move it inside
  a function, and do not add closure variables.
- All mutable state lives in `st.session_state` (`replay_idx`, `replaying`,
  `engine`, `signals`, `fvg_df`, `sweeps_df`, `learning_pause`, `learning_event`).
  The candle slider and `replay_idx` are deliberately synced before the widget
  renders (`app.py:778`) — reordering that breaks stepping.
- Adding a strategy means: a `*_strategy(df, ...) -> pd.Series` function, an entry
  in `STRATEGY_NAMES`, a branch in `get_signals`, and a blurb in
  `get_strategy_description`.
- `data_fetcher.PERIOD_MAP` / `INTRADAY_LIMIT_DAYS` encode Yahoo's interval→history
  limits; the Period dropdown is driven by `get_available_periods(interval)` so
  users can't pick an unsupported pair.

## SentimentFinance — architecture

`lexicon.py` (data) → `feed.py` (parse) → `sentiment.py` (score) → `analyze.py` (CLI).
Standard library only, by design — adding a dependency changes the project's premise.

- `lexicon.py` holds `POSITIVE`/`NEGATIVE` weights (−3…+3), `NEGATORS`, and
  `INTENSIFIERS`. This is the tuning surface; scoring logic rarely needs to change.
- `score_text` tokenises, applies an adjacent intensifier (checking **both**
  neighbours, each modifier consumed once), flips sign on a negator within
  `NEGATION_WINDOW` tokens, then squashes with `tanh(raw / SQUASH)` into [−1, 1] so
  long headlines can't outweigh short ones.
- `BULLISH = 0.15` / `BEARISH = -0.15` set the three-way split;
  `TickerSentiment` adds momentum (latest day vs. prior days) and a confidence
  grade from sample size and agreement.
- Feed format is `date | TICKER | headline`; blank lines and `#` comments skipped,
  malformed lines raise with a line number. `data/headlines.txt` is mock data.

## Conventions

- Python 3.10+ syntax (`X | None`, `from __future__ import annotations`), full type
  hints on public functions, module docstrings explaining *why* not *what*.
- `modules/*.py` must stay Streamlit-free and side-effect-free — pure functions
  taking/returning dicts, DataFrames, and dataclasses. All `st.*` calls live in
  `app.py`. This is what makes the models testable from a REPL.
- Private helpers are `_`-prefixed and grouped under `# ── section ──` comment rules.
- Both dashboards are finance-grade dark themes; Plotly figure construction belongs
  in `charts.py` / `chart_renderer.py`, never inline in `app.py`.
- These are educational/paper-trading tools. Keep the disclaimers — nothing here
  should be framed as investment advice.
