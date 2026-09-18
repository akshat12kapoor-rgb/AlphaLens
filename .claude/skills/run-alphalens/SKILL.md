---
name: run-alphalens
description: Build, run, and drive AlphaOS - the financial analysis and trading simulation platform in the AlphaLens folder (root app.py) - and its four surfaces (stock_simulator, stock-valuation-dashboard, SentimentFinance, AlgoBacktester). Use when asked to run, start, build, test, screenshot, or interact with AlphaOS, AlphaLens, the overview, valuation, news sentiment, backtester or trading simulator.
---

AlphaOS is one Streamlit app (root `app.py`) over four tools that share an active
ticker: **Overview**, **Valuation** (DCF + comparables), **News Sentiment**,
**Strategy Backtester** and **Trading Simulator**. Valuation and the simulator are
the surfaces' own `app.py` files running embedded; sentiment and the backtester
are platform pages over SentimentFinance and AlgoBacktester. Every surface still
runs standalone too.

Drive it headlessly with `.claude/skills/run-alphalens/driver.py`: it runs the real
app scripts through `streamlit.testing.v1.AppTest`, clicking buttons and reading
back `st.session_state`, with no browser. Use `shot.py` (Playwright + Chromium
against a live server) for screenshots and for the checks AppTest can't do: the
timer-driven replay, the handoff navigation and the ticker picker.

Paths are relative to the platform root (`AlphaLens/`). Verified on macOS 25.5
(arm64), Python 3.14.6, streamlit 1.63 and 1.64.

## Prerequisites

No system packages. One shared venv serves the platform and every surface:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt playwright
.venv/bin/playwright install chromium
```

Chromium is only for `shot.py`; no system Chrome needed.

## Run (agent path) - the driver

Offline against committed fixtures by default: no network, identical numbers
every run.

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py all
```

Runs each standalone surface, then AlphaOS, each in its own process, and prints
`ALL PASS`. Warm: ~7s.

**Timing on a cold machine:** the first run after `pip install` takes ~10 min for
`all` and up to ~18 min for `shot.py`, because Streamlit and its dependencies
byte-compile on first import in each subprocess. It has not hung. Warm runs:
`all` 7s, `platform` 2-3s, `sim`/`val` 5s, `sent`/`bt`/`engine` 1s, `shot.py
platform` 24s, `shot.py both` 22s.

### AlphaOS

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py platform
```

One process, one session, asserting as it goes:

1. **Overview**: all five cards render (last close $333.08, 🔴 SELL, BULLISH news,
   SMA 20/50 +10.1%, RSI 63).
2. **Valuation**: the page's signal equals the overview card, then the slider
   flow (SELL at defaults, 🟢 BUY at 35% growth / 7% WACC).
3. **Backtester**: SMA 20/50 +10.14% matches the overview card; three charts
   including the sweep heatmap; MACD long-only +25.37% vs long/short -2.51%;
   sample-CSV source.
4. **Handoff**: clicks "Replay … in the Trading Simulator"; the simulator arrives
   with 500 candles loaded and the strategy selected.
5. **Simulator**: BUY → step 3 → SELL (+44.28) → SELL flips short; 300-candle
   auto replay.
6. **News sentiment**: ad hoc headline -0.245 Bearish; mock AAPL news BULLISH
   +0.235 (identical to the CLI's AAPL score); sample feed with 5 tickers, BA
   BEARISH.
7. **Shared ticker**: picker → MSFT; valuation follows; the simulator keeps its
   AAPL session and warns `Showing AAPL. Fetch Data to load MSFT.`

Live data, any symbol (`--live` goes **before** the subcommand):

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py --live --ticker MSFT platform
```

With fixtures, every symbol returns AAPL data relabelled, so an MSFT valuation
header reads "Apple Inc. `MSFT`". That's expected offline.

### Surfaces standalone

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py sim
.venv/bin/python .claude/skills/run-alphalens/driver.py val
.venv/bin/python .claude/skills/run-alphalens/driver.py sent
.venv/bin/python .claude/skills/run-alphalens/driver.py bt
```

- `sim` drives the signed-holdings model end to end, then an auto-strategy replay
  with performance metrics.
- `val` asserts the verdict moves with the sliders.
- `sent` runs the CLI (text, feed, `--json`) plus its unit tests.
- `bt` runs AlgoBacktester's CLI, asserts AlphaOS's strategy lab reproduces it to
  the cent ($10,611.57, 8 trades), then backtests the simulator's strategies on
  the sample CSV.

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py sim --strategy "MACD Strategy" --candles 400
.venv/bin/python .claude/skills/run-alphalens/driver.py val --growth 20 --wacc 8
```

Strategies: `Manual Trading`, `RSI Strategy`, `MACD Strategy`, `MA Crossover`,
`FVG Strategy`, `Liquidity Sweep`.

### Direct invocation (no Streamlit)

For PRs touching simulator internals:

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py engine
```

For the backtester and strategy lab, import `shell.strategy_lab`. It has no
Streamlit dependency:

```bash
.venv/bin/python -c "
from shell import strategy_lab as lab
r = lab.run(lab.load_sample(), 'RSI Strategy', allow_short=True)
print(r.result.strategy, f'{r.result.total_return:+.2%}', r.result.trades)"
```

## Screenshots

```bash
.venv/bin/python .claude/skills/run-alphalens/shot.py platform
```

Walks AlphaOS in Chromium with the offline server:
overview → valuation → news sentiment → backtester → the handoff button → play and
pause the replay → away and back → type MSFT into the ticker picker.

It writes `alphaos-overview.png`, `alphaos-valuation.png`,
`alphaos-sentiment.png`, `alphaos-backtester.png`,
`alphaos-simulator-playing.png` and `alphaos-simulator.png` to
`.claude/skills/run-alphalens/shots/`.

It also asserts and prints:
- `handoff landed on simulator with data loaded`
- `candle 51 -> 67 after ~4s of play`
- the candle unchanged after leaving and returning
- `valuation follows the picker: 'Valuing MSFT'`

**Open the PNGs and look at them.** A broken page still writes a file.

Standalone apps: `shot.py both` writes `sim-landing.png`, `sim-loaded.png`,
`sim-stepped.png`, `val-dashboard.png`, `val-fullpage.png`.

## Run (human path)

From the root, so `.streamlit/config.toml` applies (dark theme, no Deploy button):

```bash
.venv/bin/streamlit run app.py
```

Live Yahoo data on http://localhost:8501. On a machine that has never run
Streamlit, the terminal first asks for an email address; press Enter. **From a
script or background job that prompt blocks forever**, so agents add
`--server.headless true`:

```bash
.venv/bin/streamlit run app.py --server.headless true
```

Offline, with price, fundamentals and news fixtures:

```bash
.venv/bin/python .claude/skills/run-alphalens/serve.py platform --port 8501
```

The standalone surfaces:

```bash
.venv/bin/python .claude/skills/run-alphalens/serve.py sim --port 8502
.venv/bin/python .claude/skills/run-alphalens/serve.py val --port 8503
cd AlgoBacktester && python3 backtester.py data/SAMPLE.csv --fast 20 --slow 50
```

`serve.py` takes `--live` for real data. Ctrl-C stops a server.

## Test

```bash
cd SentimentFinance && python3 -m unittest discover -s tests -t .
```

That's the only unit-test suite (23 tests, SentimentFinance). Everything else is
covered by the driver, which asserts rather than prints.

## Gotchas

- **Surface code lives under private aliases inside AlphaOS.** The simulator and
  valuation apps both ship a top-level `modules` package. `shell/surfaces.py`
  loads each once as `_alphalens_simulator_modules` /
  `_alphalens_valuation_modules` and execs the surface `app.py` with a per-script
  `__import__` that rewrites `modules`.
  - In platform code, tests and fixture patches, use
    `surfaces.module(surfaces.SIMULATOR, "data_fetcher")`; `import modules.x`
    doesn't work there.
  - Swapping `sys.modules` per page would race, because Streamlit runs each
    session on its own thread. Verified with two live browser sessions: one
    replaying while the other rendered valuation and sentiment 13-17 times, three
    runs, no errors.
  - Outside AlphaOS, never import both surfaces' `modules` in one interpreter.
    Whichever is first on `sys.path` wins, and the other fails with
    `ModuleNotFoundError: No module named 'modules.trading_engine'`. That's why
    `driver.py all` uses subprocesses.
- **Embedded surfaces check `ALPHAOS_EMBEDDED`.** `surfaces.run` injects it into the
  script globals. When set:
  - Both apps skip `set_page_config`, their own branding and their own ticker
    picker, and read `st.session_state["alphaos_ticker"]`.
  - The simulator also consumes `st.session_state["alphaos_sim_request"]` (the
    backtester handoff) *before* its sidebar widgets render.

  Standalone runs never see the flag.
- **`alphaos_ticker` is the one shared key.** Only the sidebar picker in `app.py`
  sets it (`shell/context.py`). The picker initialises it on first render, so
  it always exists.
- **The simulator's strategy radio has no key.** Its index comes from
  `session_state["strategy"]`, so set that and rerun to change strategy. BUY and
  SELL buttons exist only under Manual Trading, so `cmd_sim` selects it first
  (a handoff may have chosen another strategy).
- **Two `$` in Streamlit markdown open a LaTeX span.** A caption like
  `Fair value $167 · price $333` renders as a garbled math span. Captions and
  metric deltas that contain currency go through `market.md()`, which escapes
  `$`. Metric *values* are not markdown.
- **The overview must match the tools.** Its valuation card uses
  `market.DEFAULT_VALUATION`, a copy of the valuation page's slider defaults. If
  those defaults change in `stock-valuation-dashboard/app.py`, update the copy.
  `driver.py platform` fails if the card and the page disagree.
- **Currency is inconsistent across tools.** The overview picks ₹ for `.NS`/`.BO`
  symbols and `$` otherwise. The embedded valuation page hardcodes `$`, and the
  simulator hardcodes `₹` for every ticker. RELIANCE.NS shows ₹1,248 on the
  overview and $1,248.00 on Valuation.
- **Yahoo's news feed for a ticker includes broader market stories.** A live AAPL
  run returned a Walmart article. The sentiment page says so.
- **`AppTest.switch_page` only accepts file-backed pages**, which is why pages
  are thin scripts in `views/`. Pass `views/simulator.py`, not the url path.
  Segmented controls appear as `at.button_group(key=...)`.
- **Material icons are part of nav link names**
  (`candlestick_chart Trading Simulator`). In Playwright, select
  `[data-testid="stSidebarNavLink"][href$="/simulator"]`. Navigate by clicking;
  loading a URL starts a fresh session.
- **During ▶ replay only the chart redraws.** The `· 51 / 500` header badge
  updates on the rerun that ⏸ triggers, so read the position after pausing.
  Click ▶ only once the page has settled, and wait for ⏸ to appear, or the click
  can be lost. An early concurrency test failed exactly this way.
- **The simulator's CSS hides every `<header>`**, including the nav section
  labels. `app.py` injects an override for `stNavSectionHeader`.
- **`AppTest.session_state` has no `.get()`.** Use `ss["key"]` / `"key" in ss`.
- **AppTest cannot tick `@st.fragment(run_every=0.25)`.** `cmd_sim` advances
  `replay_idx` and makes the fragment's engine calls itself. `⏭+1` works under
  AppTest; `▶` doesn't.
- **Click buttons by label, not index.** Indexes shift when the replay controls
  appear.
- **`calculate_performance_metrics` takes `(trade_history, portfolio_history,
  initial_capital)`**, not the engine.
- **The valuation app fetches on first run.** Patch its fetcher *before*
  `AppTest.from_file(...).run()`. `shell.market.news` looks up `fetch_news` at
  call time so it can be patched.
- **Raw `curl` to Yahoo gets HTTP 429, but yfinance works** (it uses
  `curl_cffi` impersonation). Test the network with yfinance.
- **Requirement floors resolve to much newer versions** (pandas 3.0, streamlit
  1.63/1.64, plotly 7.x). It works. The valuation app's `use_container_width=`
  warns repeatedly; that's noise, not failure.
- **Port behaviour depends on whether you set it.** Plain `streamlit run app.py`
  quietly moves to the next free port (8502, ...) when 8501 is taken, so a
  forgotten server makes the URL change. With an explicit `--server.port` (as
  `serve.py` passes) Streamlit exits with `Port 8501 is not available` instead.
  Find the old server with `lsof -nP -iTCP:8501 -sTCP:LISTEN` and stop it.
  `shot.py` picks free ports itself.
- **macOS has no `timeout(1)`.**
- **Git layout.** The root is its own repo (github.com/akshat12kapoor-rgb/AlphaLens)
  tracking the platform files. Each of the four surfaces is a separate repo,
  excluded by the root `.gitignore` so they aren't recorded as gitlinks. Commit
  surface changes with `git -C <surface>`.

## Fixtures

- `fixtures/AAPL_1d.csv`: 500 real daily AAPL candles (2024-09-16 → 2026-09-14).
- `fixtures/AAPL_fundamentals.json`: a real `fetch_stock_data("AAPL")` result,
  with Series stored as `{"__series__": {...}}`.
- `fixtures/AAPL_news.json`: **mock** stories built from the AAPL lines of
  `SentimentFinance/data/headlines.txt`, in `shell.market.fetch_news`'s shape.
  Real headlines aren't committed.

The numbers quoted in this skill depend on these snapshots. Recapturing them
changes the numbers.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'modules.trading_engine'` | Both surfaces' `modules` in one interpreter. Standalone: one per process. AlphaOS: `shell.surfaces.module(...)`. |
| Overview card text garbled, `$` amounts missing | Unescaped `$` pair in markdown. Wrap with `market.md()`. |
| `KeyError: st.session_state has no key "alphaos_ticker"` in a test | The picker initialises it on first render; run `app.py` once before reading it. |
| `button 'BUY' not found` after a handoff | The handoff selected an auto strategy; set `session_state["strategy"] = "Manual Trading"` and rerun. |
| `ValueError: Could not find page 'simulator' relative to the main script` | `AppTest.switch_page("views/simulator.py")`. |
| Playwright times out on `get_by_role("link", name="Trading Simulator")` | Select `stSidebarNavLink` by `href`. |
| Replay "doesn't advance" in a browser test | ▶ was clicked mid-rerun. Wait for the ⏸ button before measuring. |
| `AttributeError: get not found in session_state` | Use `ss["key"]`. |
| `TypeError: 'TradingEngine' object is not iterable` | `calculate_performance_metrics(engine.trade_history, ...)`. |
| `Port 8501 is not available`, server exits | `lsof -ti:8501 \| xargs kill -9`, or `--port`. |
| App opens on :8502 instead of :8501 | An earlier server still holds 8501; stop it or use the printed URL. |
| Background `streamlit run app.py` never healthy | First-run email prompt. Add `--server.headless true`. |
| Valuation shows "Insufficient cash-flow data" | Expected for crypto/ETFs (e.g. BTC-USD). The other tools still work. |
| `playwright._impl._errors.Error: Executable doesn't exist` | `.venv/bin/playwright install chromium` |
