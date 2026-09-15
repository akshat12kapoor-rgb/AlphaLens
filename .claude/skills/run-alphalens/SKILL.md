---
name: run-alphalens
description: Build, run, and drive AlphaLens - the retail-investor platform with three surfaces (stock_simulator replay/paper-trading, stock-valuation-dashboard DCF, SentimentFinance CLI). Use when asked to run, start, build, test, screenshot, or interact with AlphaLens or any of its three surfaces.
---

AlphaLens is one platform with three surfaces: a **simulator** (Streamlit candle
replay + paper trading), a **valuation dashboard** (Streamlit DCF/multiples), and
a **sentiment** CLI (stdlib only). All three are driven headlessly by one script,
`.claude/skills/run-alphalens/driver.py`, which runs the real `app.py` through
`streamlit.testing.v1.AppTest` - it clicks buttons and reads back
`st.session_state`, no browser required. Screenshots come from `shot.py`
(Playwright + Chromium against a live server).

All paths below are relative to the platform root (`AlphaLens/`). Verified on
macOS 25.5 (arm64), Python 3.14.6.

## Prerequisites

No system packages needed. One shared venv serves all three surfaces - the two
Streamlit apps' requirements are compatible, and the sentiment CLI needs nothing.

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
cat stock_simulator/requirements.txt stock-valuation-dashboard/requirements.txt \
  | grep -v '^#' | grep -v '^$' | sort -u > /tmp/alphalens-reqs.txt
.venv/bin/pip install -r /tmp/alphalens-reqs.txt playwright
```

Chromium is only needed for screenshots (no system Chrome required):

```bash
.venv/bin/playwright install chromium
```

## Run (agent path) - the driver

Everything runs offline against committed fixtures by default, so it works with
no network and gives byte-identical numbers every time.

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py all
```

That runs all three surfaces, each in its own process, and prints `ALL PASS`.

**Timing:** the *first* run after a fresh `pip install` is very slow - ~10 min for
`all`, ~18 min for `shot.py both` - because Streamlit and its ~50 dependencies
byte-compile on first import, once per subprocess. Warm runs are fast: `all` 11s,
`sim`/`val` 5s each, `sent`/`engine` 1s, `shot.py both` 22s. Don't kill the first
run thinking it hung; budget 20 minutes for a cold machine.

Individual surfaces:

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py sim
.venv/bin/python .claude/skills/run-alphalens/driver.py val
.venv/bin/python .claude/skills/run-alphalens/driver.py sent
```

`sim` boots the app, clicks **Fetch Data**, then exercises the signed-holdings
model end to end - BUY opens a long, `⏭+1` steps three candles, SELL closes it
for a realized P&L, a second SELL flips to short - then replays 300 candles on a
strategy and prints performance metrics. Options:

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py sim \
  --strategy "MACD Strategy" --candles 400
```

Valid strategies: `Manual Trading`, `RSI Strategy`, `MACD Strategy`,
`MA Crossover`, `FVG Strategy`, `Liquidity Sweep`.

`val` renders the dashboard, reads the verdict, then moves the sidebar
assumptions and asserts the verdict actually moves (at 10%/10% AAPL reads
🔴 SELL; at 35% growth / 7% WACC it flips 🟢 BUY):

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py val --growth 20 --wacc 8
```

Live market data instead of fixtures (global flag, goes **before** the
subcommand):

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py --live --ticker MSFT sim --candles 100
```

### Direct invocation (no Streamlit)

Most PRs touch `modules/` internals, not the UI. This path skips Streamlit
entirely and is by far the fastest check:

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py engine
```

It loads the fixture, computes indicators and SMC zones, prints the signal
distribution for all six strategies, and runs a long→flat→short flip through
`TradingEngine`.

## Screenshots

```bash
.venv/bin/python .claude/skills/run-alphalens/shot.py both
```

Writes PNGs to `.claude/skills/run-alphalens/shots/`:
`sim-landing.png`, `sim-loaded.png`, `sim-stepped.png` (the driver clicks Fetch
Data and steps the replay), `val-dashboard.png`, `val-fullpage.png`.
`shot.py` picks a free port itself, so it never collides with a server you left
running. **Open the PNG and look at it** - a blank page still writes a file.
Expect ~22s warm (much longer on the first run after install, see Timing above).
`sim-loaded.png` should show the candlestick chart with the green
"Loaded 500 candles for AAPL · 161 FVGs · 59 Sweeps detected" banner;
`sim-stepped.png` should show the slider at 53 and the header badge at
`29 Nov 2024 · 54 / 500`, proving the replay actually advanced.

## Run (human path)

```bash
.venv/bin/python .claude/skills/run-alphalens/serve.py sim --port 8501
.venv/bin/python .claude/skills/run-alphalens/serve.py val --port 8502
```

`serve.py` is a real Streamlit server with the fixture pre-wired, so the page
renders loaded data with no network. Add `--live` for real Yahoo data. Ctrl-C to
stop. Plain `streamlit run app.py` from inside either app directory also works,
but it fetches live on load and both apps default to the same port.

## Test

```bash
cd SentimentFinance && python3 -m unittest discover -s tests -t .   # 23 tests
```

That is the **only** test suite in the platform. Neither Streamlit app has one -
`driver.py sim` / `val` are the regression check for those, and they assert, not
just print.

Single test:

```bash
cd SentimentFinance && python3 -m unittest tests.test_sentiment -v
```

## Gotchas

- **Both Streamlit apps ship a top-level package named `modules`.** Put both on
  `sys.path` in one process and whichever is first wins; the other's imports die
  with a baffling `ModuleNotFoundError: No module named 'modules.trading_engine'`.
  This is why `driver.py all` re-execs itself as subprocesses instead of looping
  in-process, and why `use()` inserts exactly one component path. Never import
  from both apps in the same interpreter.
- **`AppTest.session_state` has no `.get()`.** It is a `SafeSessionState` whose
  `__getattr__` forwards into the state dict, so `ss.get("data_loaded")` raises
  `AttributeError: get not found in session_state`. Use `ss["key"]` and
  `"key" in ss`.
- **The replay loop is `@st.fragment(run_every=0.25)` and AppTest cannot tick
  it.** `at.run()` will never advance the replay on its own. To simulate replay,
  advance `session_state["replay_idx"]` yourself and make the same
  `engine.buy/sell` calls the fragment makes - that is what `cmd_sim` does. The
  `⏭+1` button *does* work under AppTest; only the timer-driven `▶` does not.
- **Click buttons by label, never by index.** `at.button[0]` is `🔄 Fetch Data`
  before data loads and `⏮` after, because loading data reveals the replay
  controls ahead of the sidebar in render order.
- **`calculate_performance_metrics` takes `(trade_history, portfolio_history,
  initial_capital)`, not the engine.** Passing the engine fails late with
  `TypeError: 'TradingEngine' object is not iterable`.
- **The valuation app fetches on import.** `should_run = run_btn or
  (stock_data is None)`, so the very first `at.run()` hits Yahoo before you can
  click anything. Patch `modules.data_fetcher.fetch_stock_data` *before*
  `AppTest.from_file(...).run()`.
- **Raw `curl` to Yahoo Finance returns HTTP 429, but yfinance works.** yfinance
  ships `curl_cffi` browser impersonation. Do not conclude the network is down
  from a failing `curl` - test with `yfinance` itself.
- **`requirements.txt` only sets floors, so a fresh install today resolves to
  pandas 3.0.5 / numpy 2.5.3 / streamlit 1.63 / plotly 7.0** - far newer than
  what the code was written against. It all still works, but
  `stock-valuation-dashboard/app.py` calls `use_container_width=`, which
  Streamlit says is removed after 2025-12-31; it currently only warns, loudly and
  repeatedly. `stock_simulator` already migrated to `width="stretch"`. Pin the
  requirements or migrate the valuation app before this becomes a hard break.
- **Both apps default to port 8501.** Streamlit does not fall back to another
  port - it prints `Port 8501 is not available` and exits. A server you
  backgrounded earlier will silently break the next launch:
  `lsof -ti:8501 | xargs kill -9`.
- **macOS has no `timeout(1)`.** Don't wrap these commands in it; it's GNU
  coreutils (`brew install coreutils` gives `gtimeout`).
- **Streamlit paints over a websocket**, so the DOM is empty for a beat after
  `goto`. Wait for real content - `.js-plotly-plot` for a chart,
  `[data-testid="stMetric"]` for the valuation metrics - not a fixed sleep.
- **`AlphaLens/` itself is not a git repo**; the three surfaces are three
  separate repos with their own remotes. This skill and its fixtures are
  therefore untracked by anything. Also note `stock_simulator/.gitignore`
  ignores `.claude`, so the skill deliberately lives at the platform root
  instead. Run git commands with `-C <surface>`.
- The sentiment CLI needs **no venv** - it is stdlib only and runs on system
  `python3`. `driver.py sent` invokes it with `sys.executable` from the venv,
  which works too.

## Fixtures

`fixtures/AAPL_1d.csv` - 500 real daily AAPL candles (2024-09-16 → 2026-09-14),
captured from Yahoo. `fixtures/AAPL_fundamentals.json` - a real
`fetch_stock_data("AAPL")` result, with pandas Series stored as
`{"__series__": {...}}` and rehydrated on load.

Refresh them when you want newer data:

```bash
cd stock_simulator && PYTHONPATH=. ../.venv/bin/python -c "
from modules.data_fetcher import fetch_data
fetch_data('AAPL','2y','1d').to_csv('../.claude/skills/run-alphalens/fixtures/AAPL_1d.csv')"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'modules.trading_engine'` | You imported both apps in one process. Run one surface per process. |
| `AttributeError: get not found in session_state` | `AppTest` state has no `.get()`; use `ss["key"]`. |
| `TypeError: 'TradingEngine' object is not iterable` | `calculate_performance_metrics` wants `trade_history`, not the engine. |
| `Port 8501 is not available` then the server exits | `lsof -ti:8501 \| xargs kill -9`, or pass `--port`. |
| `driver.py` exits 1 with `data_loaded False` | Live fetch failed (bad ticker or Yahoo throttling). Drop `--live` to use fixtures. |
| Screenshot is blank / all dark | You didn't wait for the websocket paint. `shot.py` waits on `.js-plotly-plot`; keep that. |
| `playwright._impl._errors.Error: Executable doesn't exist` | `.venv/bin/playwright install chromium` |
| Repeated `use_container_width will be removed` warnings | Expected from the valuation app. Noise, not failure. |
