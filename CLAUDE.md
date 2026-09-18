# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Platform shape

**AlphaOS** is a financial analysis and trading simulation platform: one Streamlit
app (root `app.py`) over four tools that share an active ticker. The folder and
root GitHub repo are still named AlphaLens.

| Page | Built from | What it does |
|---|---|---|
| Overview | `shell/home.py` | The active ticker through every tool at once |
| Valuation | `stock-valuation-dashboard/app.py` (embedded) | DCF + comparable multiples → BUY/HOLD/SELL |
| News Sentiment | `shell/sentiment_page.py` over `SentimentFinance/` | Lexicon scoring of live Yahoo headlines, sample or uploaded feeds |
| Strategy Backtester | `shell/backtest_page.py` over `AlgoBacktester/` | Backtest SMA crossover and every simulator strategy, sweep parameters |
| Trading Simulator | `stock_simulator/app.py` (embedded, repo `TradingSimTALP`) | Candle-by-candle replay + paper trading |

- **Every surface still runs standalone.**
- **Each of the four surface directories is its own git repo** with its own
  remote.
- **The root repo tracks only platform files** (`app.py`, `shell/`, `views/`,
  `.streamlit/`, `requirements.txt`, `CLAUDE.md`, `.claude/`). Its `.gitignore`
  excludes all four surface directories on purpose: `git add` on a directory that
  contains a `.git` records a gitlink (mode 160000), not the contents.
- A feature often spans repos: platform code in the root plus an
  `ALPHAOS_EMBEDDED` branch in a surface. Commit each with `git -C <dir>`.

## AlphaOS architecture

```
app.py                  st.navigation over views/*.py; sidebar ticker picker; CSS override
shell/context.py        the active ticker (session_state["alphaos_ticker"]) + picker
shell/market.py         cached price history / fundamentals / news, default valuation, md()
shell/strategy_lab.py   AlgoBacktester engine x simulator signals; no Streamlit
shell/surfaces.py       loads and execs the embedded surfaces
views/*.py              one-line page scripts calling the above
```

- **The simulator and valuation apps both ship a top-level package named
  `modules`**, so they can't share `sys.modules`. `shell/surfaces.py` loads each
  package once under a private alias (`_alphalens_simulator_modules`, ...). It
  then execs the surface's `app.py` with a per-script `__import__` that rewrites
  `modules` to that alias. It deliberately doesn't swap `sys.modules` per page:
  Streamlit runs each browser session on its own thread, so swapping would race.
  - In platform code, reach surface code via
    `surfaces.module(surfaces.SIMULATOR, "trading_engine")`, never
    `import modules.x`.
  - Surface packages must keep not importing each other as `modules.<x>`.
  - Outside AlphaOS, never import both surfaces' `modules` in one interpreter.
    Whichever is first on `sys.path` wins, and the other fails with
    `ModuleNotFoundError: No module named 'modules.trading_engine'`.
  - SentimentFinance and AlgoBacktester are flat stdlib modules with no clash;
    `use_sentiment()` / `use_backtester()` put them on `sys.path`.
- **Embedded mode.** `surfaces.run` injects `ALPHAOS_EMBEDDED = True` into the
  script globals. The simulator and valuation apps check
  `globals().get("ALPHAOS_EMBEDDED", False)`, and when it's set they:
  - skip `set_page_config`, their own branding and their own ticker picker;
  - read `st.session_state["alphaos_ticker"]` instead.

  Keep new platform-driven behaviour behind that flag, so standalone runs don't
  change.
- **Cross-tool handoff.** The backtester writes
  `st.session_state["alphaos_sim_request"]` (`ticker`, `strategy`, `interval`,
  `period`) and calls `st.switch_page`. The simulator consumes the request
  before its sidebar widgets render, then loads data with the strategy selected.
- **One source of numbers.**
  - Platform pages fetch through the surfaces' own fetchers (via
    `shell.market`), so every tool sees the same data and a fixture patched into
    a fetcher applies everywhere.
  - The overview's valuation card uses `market.DEFAULT_VALUATION`, a copy of the
    valuation page's slider defaults. Change both together; `driver.py platform`
    asserts they match.
  - The sentiment page calls the same functions as `SentimentFinance/analyze.py`.
- **Backtest semantics.** `strategy_lab.SignalStrategy` holds the direction of
  the latest simulator BUY/SELL signal. The AlgoBacktester engine trades a
  bar-*i* position over the *i* → *i*+1 return, fully invested. None of the
  simulator's signals look ahead:
  - RSI, MACD and MA use the current and previous bar.
  - Sweeps compare against the prior 20 bars.
  - An FVG fires only once its third candle closes.

  Keep that true for new strategies. Backtests are daily bars only, since the
  engine annualises with 252.
- **Streamlit markdown treats a pair of `$` as LaTeX.** Pass captions and metric
  deltas that contain currency through `market.md()`.
- **Known gap: currency.** The overview uses ₹ for `.NS`/`.BO` symbols, but the
  valuation app hardcodes `$` and the simulator hardcodes `₹` for every ticker.
- Surface `app.py` edits apply on the next rerun (`surfaces._code` recompiles on
  mtime change). Edits inside a surface's `modules/` need a server restart.
- Pages are files in `views/`, not callables, because `AppTest.switch_page` can
  only select file-backed pages.
- Session-state keys must stay distinct across tools. The platform uses the
  `alphaos_` prefix; the backtester and sentiment pages use `bt_` and
  `sentiment_`.
- `.streamlit/config.toml` (dark theme, minimal toolbar) applies only when
  Streamlit is launched from the root.

## Running it

Start with the run skill at `.claude/skills/run-alphalens/`. It's verified end to
end and drives AlphaOS and each surface headlessly against committed offline
fixtures:

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py all
```

Launch AlphaOS (live Yahoo data) from the root:

```bash
.venv/bin/streamlit run app.py
```

One shared root venv serves everything (`pip install -r requirements.txt`). The
skill covers setup, the offline server (`serve.py platform`), screenshots
(`shot.py platform`) and gotchas.

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

The backtester CLI is stdlib-only too:

```bash
cd AlgoBacktester && python3 backtester.py data/SAMPLE.csv --fast 20 --slow 50
```

Only SentimentFinance has unit tests, and nothing has a linter config. The run
skill's `driver.py sim` / `val` / `bt` / `platform` commands are the regression
check for the rest; they assert rather than just print. Verify `modules/` changes by importing them
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

## AlgoBacktester — architecture

`data_loader.py` (CSV → `PriceSeries` of `Bar`s) → `strategies/` (`Strategy`
subclasses return one target position per bar in [-1, 1]) → `backtester.py`
(`run_backtest` → `BacktestResult` with CAGR, Sharpe, drawdown, win rate,
exposure). Stdlib only.

- The engine holds `positions[i]` over the return from bar *i* to *i*+1, and charges
  `commission` on turnover. A strategy may only use bars up to and including *i*.
- `load_csv` sorts by date and rejects duplicates. `PriceSeries` built directly
  (as AlphaOS does from Yahoo data) skips that check, so `strategy_lab` rejects
  intraday data itself.
- `MovingAverageCrossover.name` is an instance attribute (`sma_20_50`);
  `strategy_lab` overrides it with a readable name for display.

## Conventions

- Python 3.10+ syntax (`X | None`, `from __future__ import annotations`), full type
  hints on public functions, module docstrings explaining *why* not *what*.
- `modules/*.py` must stay Streamlit-free and side-effect-free — pure functions
  taking/returning dicts, DataFrames, and dataclasses. All `st.*` calls live in
  `app.py`. This is what makes the models testable from a REPL.
- Private helpers are `_`-prefixed and grouped under `# ── section ──` comment rules.
- Surface dashboards keep Plotly figure construction in `charts.py` /
  `chart_renderer.py`, not inline in `app.py`. Platform pages build their figures
  in the page module.
- AlphaOS is dark-themed throughout; charts use `template="plotly_dark"` with
  transparent backgrounds.
- These are educational/paper-trading tools. Keep the disclaimers — nothing here
  should be framed as investment advice.
