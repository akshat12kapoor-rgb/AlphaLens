---
name: run-alphalens
description: Build, run, test and drive AlphaOS - the financial analysis and trading simulation platform in the AlphaLens repo (app.py plus the alphalens package). Use when asked to run, start, build, test, screenshot or interact with AlphaOS, AlphaLens, the overview, valuation, news sentiment, backtester or trading simulator, or to run the sentiment or backtest CLIs.
---

AlphaOS is one Streamlit app (`app.py`) over four tools that share an active
ticker: **Overview**, **Valuation**, **News Sentiment**, **Strategy Backtester**
and **Trading Simulator**. All the logic lives in the `alphalens` package;
`views/` holds one thin script per page. Nothing below `alphalens/ui` imports
Streamlit, so the package, its two CLIs and the tests run without a server.

Drive it headlessly with `.claude/skills/run-alphalens/driver.py`, which runs the
real `app.py` through `streamlit.testing.v1.AppTest` - clicking widgets, reading
back session state, no browser. Use `shot.py` for screenshots and for the checks
AppTest cannot do.

Paths are relative to the repo root. Verified on macOS 25.5 (arm64), Python
3.14.6, streamlit 1.63.

## Prerequisites

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium
```

`requirements.txt` is the app; `requirements-dev.txt` adds pytest and Playwright.
Chromium is only needed for `shot.py`; no system Chrome required.

## Run (agent path)

Offline against committed fixtures by default - no network, identical numbers
every run.

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py all
```

Runs four stages, each in its own process, and prints `ALL PASS`: `tests`, `cli`,
`lab` and `app`. Warm: ~5s.

**Cold machine:** the first run after `pip install` takes several minutes while
Streamlit and its dependencies byte-compile. It has not hung.

### Stages

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py tests   # pytest, 157 tests
.venv/bin/python .claude/skills/run-alphalens/driver.py cli     # both command lines
.venv/bin/python .claude/skills/run-alphalens/driver.py lab     # the package, no Streamlit
.venv/bin/python .claude/skills/run-alphalens/driver.py app     # every page, one session
```

`lab` is the fastest check when changing the maths: it prints each strategy's
signal counts and backtest, asserts the sample MA 20/50 backtest still ends at
$10,611.57, and values the AAPL fixture.

`app` asserts as it goes:

1. **Overview**: five cards render (last close $333.08, 🔴 SELL, BULLISH news,
   MA 20/50 +10.1%, RSI 63).
2. **Valuation**: the page's signal equals the overview card; growth 35% / WACC
   7% flips it to 🟢 BUY; five charts including the sensitivity heatmap.
3. **Backtester**: MA 20/50 +10.14% matches the overview card; MACD long-only
   +25.37% vs long/short -2.51%; the sample-CSV source works.
4. **Handoff**: the "Replay … in the Trading Simulator" button loads the
   simulator with 500 candles and the chosen strategy.
5. **Simulator**: BUY → step 3 → SELL (+190.40) → SELL flips short; then a
   300-candle auto replay with performance statistics.
6. **Sentiment**: ad hoc headline -0.245 Bearish; the mock AAPL news scores
   +0.235 BULLISH, exactly as the CLI scores AAPL in the sample feed; the sample
   feed has 5 tickers and BA drills down BEARISH.
7. **Shared ticker**: the picker moves valuation and the overview to MSFT while
   the simulator keeps its AAPL session and warns that it is stale.

Live data instead of fixtures (`--live` goes **before** the subcommand):

```bash
.venv/bin/python .claude/skills/run-alphalens/driver.py --live --ticker MSFT app
```

With fixtures every symbol returns the AAPL snapshot relabelled, so an MSFT
valuation header reads "Apple Inc. `MSFT`". That is expected offline.

## Screenshots

```bash
.venv/bin/python .claude/skills/run-alphalens/shot.py
```

Walks the app in Chromium against the offline server and writes
`alphaos-overview.png`, `alphaos-valuation.png`, `alphaos-sentiment.png`,
`alphaos-backtester.png`, `alphaos-simulator-playing.png` and
`alphaos-simulator.png` to `.claude/skills/run-alphalens/shots/` (~30s).

It also asserts what only a browser shows, printing each:
- `handoff landed on simulator with data loaded`
- `replay fragment in browser: candle 51 -> 68 after ~4s of play`
- the candle unchanged after leaving the page and coming back
- `picker -> MSFT: the simulator flags its loaded data as stale`
- `valuation follows the picker to MSFT`

**Open the PNGs and look at them.** A broken page still writes a file.

## Run (human path)

```bash
.venv/bin/streamlit run app.py
```

Live data on http://localhost:8501. On a machine that has never run Streamlit the
terminal asks for an email address; press Enter. **From a script or background
job that prompt blocks forever**, so add `--server.headless true`.

Offline, with the fixtures wired in:

```bash
.venv/bin/python .claude/skills/run-alphalens/serve.py --port 8501
```

Add `--live` for real data. Ctrl-C stops it.

## Command lines

```bash
.venv/bin/python -m alphalens.backtest                                    # sample data, MA 20/50
.venv/bin/python -m alphalens.backtest --symbol AAPL --strategy rsi --short
.venv/bin/python -m alphalens.sentiment --live AAPL
.venv/bin/python -m alphalens.sentiment --text "Nvidia beats estimates but warns of weak demand"
```

## Tests

```bash
.venv/bin/python -m pytest tests -q          # 157 tests, ~0.3s
.venv/bin/python -m pytest tests/test_backtest.py -q -k original
```

`tests/conftest.py` fixtures (`prices`, `enriched`, `context`, `sample`,
`fundamentals`) never touch the network.

## Gotchas

- **`data/fixtures.install()` redirects the whole app offline** by replacing the
  functions in `data/yahoo.py`. Call it *before* `AppTest.from_file(...).run()`;
  the overview fetches on first render.
- **Pages must be the files in `views/`.** `AppTest.switch_page` only accepts
  file-backed pages, so pass `views/simulator.py`, never the url path.
- **`st.switch_page` does not move AppTest**, only a real browser. After clicking
  the backtester's handoff, navigate explicitly.
- **AppTest cannot tick `st.fragment(run_every=...)`.** The replay never advances
  under AppTest; the driver drives the same engine calls instead. `⏭` works;
  `▶` needs `shot.py`.
- **A keyed widget's stored value beats its value argument.** The replay slider
  is synced through `st.session_state["sim_slider"]` before rendering - without
  that, stepping and playing are silently undone on the next rerun.
- **During ▶ only the chart redraws.** Read the replay position after pausing;
  and wait for the ⏸ button to appear before measuring, or the click is lost mid-rerun.
- **Two `$` in markdown start a LaTeX span.** Money in captions and metric deltas
  goes through `ui.layout.markdown_safe()`. In AppTest you therefore see the raw
  `\$`; the browser renders `$`.
- **Material icons are part of a nav link's name** (`calculate Valuation`), so
  Playwright must select `[data-testid="stSidebarNavLink"][href$="/valuation"]`.
  Navigate by clicking; loading a URL starts a new session.
- **Streamlit's cache needs a runtime.** `data/cache.py` uses `st.cache_data` only
  when a Streamlit runtime is running, and an lru_cache otherwise; calling
  `st.cache_data` from a CLI warns on every call.
- **Raw `curl` to Yahoo returns HTTP 429, but yfinance works** (it uses
  `curl_cffi` impersonation). Test the network with yfinance, not curl.
- **Plain `streamlit run app.py` moves to the next free port** when 8501 is busy,
  so the URL changes; with an explicit `--server.port` it exits with
  `Port 8501 is not available`. Find the old server with
  `lsof -nP -iTCP:8501 -sTCP:LISTEN`. `shot.py` picks free ports itself.
- **Streamlit symlinks its own agent skill** into `.agents/` and
  `.claude/skills/developing-with-streamlit`, pointing into `.venv`. Both are
  gitignored; committing them would push links that dangle for everyone else.
- **macOS has no `timeout(1)`.**

## Fixtures

- `fixtures/AAPL_prices.csv` - 500 real daily AAPL bars (2024-09-16 → 2026-09-14).
- `fixtures/AAPL_fundamentals.json` - a real fundamentals snapshot.
- `fixtures/AAPL_news.json` - **mock** stories built from the sample feed's AAPL
  lines, in `data.yahoo.fetch_news`'s shape. Real headlines are not committed.
- `alphalens/data/samples/` - the sample price CSV and headline feed the app
  itself offers, not test data.

The numbers quoted above depend on these snapshots; recapturing them changes the
numbers.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ValueError: Could not find page 'simulator'` | Pass `views/simulator.py` to `switch_page`. |
| Handoff test stays on the backtester | AppTest ignores `st.switch_page`; navigate explicitly. |
| Replay "doesn't advance" in a browser test | ▶ was clicked mid-rerun; wait for ⏸ first. |
| Stepping resets to the same candle | The slider's keyed state is out of sync; set it before rendering. |
| Overview card says "unavailable" for crypto | Expected: no statements, so no DCF. Other cards still work. |
| `$` missing or text garbled in a caption | Unescaped `$` pair; wrap with `layout.markdown_safe()`. |
| Backtest numbers differ between a page and the package | A raw frame reached a strategy; go through `indicators.ensure`. |
| Background `streamlit run` never answers `/_stcore/health` | The first-run email prompt. Add `--server.headless true`. |
| `playwright._impl._errors.Error: Executable doesn't exist` | `.venv/bin/playwright install chromium` |
