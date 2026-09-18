# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**AlphaLens** is one repository containing **AlphaOS**, a financial analysis and
trading simulation platform: a Streamlit app over four tools that share one
active ticker — valuation, news sentiment, strategy backtesting and a trading
simulator.

It began as four separate repositories (TradingSimTALP, stock-valuation-dashboard,
SentimentFinance, AlgoBacktester) that were merged into a single package. Those
repositories still exist on GitHub as history; nothing here depends on them.

## Architecture

```
app.py                  navigation + the sidebar ticker picker
views/<page>.py         thin scripts: import the page module and call render()
alphalens/
  core/       config.py (defaults), currency.py (symbols and formatting)
  data/       yahoo.py (the only network boundary), csv_prices.py, models.py,
              fixtures.py (offline snapshots), cache.py, samples/
  signals/    indicators.py, smc.py, strategies.py (the catalogue)
  backtest/   engine.py, sweep.py, __main__.py (CLI)
  trading/    engine.py (paper trading), performance.py
  valuation/  dcf.py, multiples.py, decision.py, analysis.py (the pipeline)
  sentiment/  lexicon.py, feed.py, scoring.py, __main__.py (CLI)
  charts/     theme.py + one module per chart family
  ui/         context.py (active ticker), layout.py, replay.py, pages/
```

Dependencies run one way: `ui` → `charts` → domain packages (`signals`,
`backtest`, `trading`, `valuation`, `sentiment`) → `data` → `core`. Nothing below
`ui` imports Streamlit, which is why the CLIs and the tests can use all of it.

### The rules that matter

- **One strategy definition.** `signals/strategies.py` holds the catalogue. A
  strategy declares the form natural to it — `events` (BUY/SELL/HOLD, what the
  simulator trades) or `regime` (a target position per bar, what the backtester
  holds) — and the other form is derived. Add a strategy there and it appears in
  both tools, with its parameters.
  - Events carry less information than positions: "close the short" and "go long"
    are both a BUY, so the round trip is exact only for always-in-market series.
- **No look-ahead.** A strategy may only use bars up to and including *i*; the
  engine applies that decision to the *i* → *i*+1 return.
  `tests/test_strategies.py::test_no_strategy_looks_ahead` asserts this for every
  strategy by recomputing on a truncated frame. Keep it passing.
- **Indicators come from one place.** Strategies call `indicators.ensure(frame)`,
  so a signal never depends on whether the caller enriched the frame first.
  (`ta` and the pandas fallback differ slightly; that discrepancy once made the
  backtester page disagree with the package.)
- **One data boundary.** Everything reaches Yahoo through `data/yahoo.py`, so
  every tool sees the same numbers and `data/fixtures.install()` can redirect the
  whole app offline in one call.
- **Currency follows the instrument.** `Quote.currency` / `Fundamentals.currency`
  come from Yahoo; `core/currency.py` formats with them. Never hardcode a symbol,
  and never format money with a bare f-string.
- **Valuation has one pipeline.** `valuation/analysis.value()` is what both the
  overview card and the valuation page call, so a summary cannot disagree with
  the page it summarises.
- **Missing data is normal.** Crypto and most ETFs have no statements;
  `Fundamentals.require(...)` raises `MissingData`, and the UI degrades that card
  rather than the page (`ui/context.attempt`).

### Streamlit specifics

- **Pages are files** in `views/` because `AppTest.switch_page` only accepts
  file-backed pages. The code lives in `alphalens/ui/pages/`.
- **The replay fragment** (`ui/replay.tick`) is defined at module level:
  `st.fragment` keys off function identity, so defining it inside a page script
  would rebuild it every rerun. While playing, only the chart redraws; anything
  that changes the rest of the page exits with `st.rerun(scope="app")`.
- **Keyed widgets win over their value argument.** The replay slider syncs
  `st.session_state["sim_slider"]` before rendering; without that, stepping and
  playing are undone by the stale widget on the next rerun.
- **Two `$` in markdown open a LaTeX span.** Captions, markdown and metric deltas
  containing money go through `ui/layout.markdown_safe()`. Metric *values* are not
  markdown and need no escaping.
- **Session state keys** are namespaced: `alphaos_` for the platform, `sim_` and
  `bt_` for page widgets, and the whole replay lives in one `Session` dataclass
  under `"simulator"`.
- **`st.switch_page` does not move AppTest**, only a browser; tests navigate
  explicitly after clicking a handoff.

## Running it

```bash
.venv/bin/streamlit run app.py                                    # the app, live data
.venv/bin/python .claude/skills/run-alphalens/driver.py all       # tests, CLIs, package, app
.venv/bin/python .claude/skills/run-alphalens/shot.py             # browser walk + screenshots
.venv/bin/python -m pytest tests -q                               # the suite alone
```

The run skill at `.claude/skills/run-alphalens/` is verified end to end and drives
everything against committed fixtures; start there. `serve.py` runs the app
offline.

## Conventions

- Python 3.10+ syntax, `from __future__ import annotations`, type hints on public
  functions, dataclasses at module boundaries.
- Module docstrings explain *why* the module exists and the decisions inside it;
  comments explain the non-obvious, not the syntax.
- Private helpers are `_`-prefixed; sections are separated with `# ── name ──`.
- Charts are built in `alphalens/charts/`, never inline in a page, and all use
  `charts/theme.py`.
- This is educational software. Keep the disclaimers, and keep the honesty
  caveats next to the numbers they qualify (in-sample sweeps, the 100% cash
  collateral proxy, sentiment not being a forecast).
