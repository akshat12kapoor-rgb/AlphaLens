#!/usr/bin/env python
"""
AlphaLens driver - launches and drives the platform headlessly.

Run from the repo root:

    .venv/bin/python .claude/skills/run-alphalens/driver.py all

Commands:
    all       tests, CLIs, package and app - each in its own process
    app       every page of AlphaLens in one session: the shared ticker, the
              backtest -> simulator handoff, and state surviving page switches
    cli       the sentiment and backtest command lines
    tests     the pytest suite
    lab       the package with no Streamlit (fastest check when changing maths)

The app is driven through streamlit.testing.v1.AppTest, which runs the real
app.py, clicks widgets and reads back session state - no browser. Use shot.py
for screenshots and for what AppTest cannot do (the timer-driven replay).

Data comes from committed fixtures by default; --live uses Yahoo Finance.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
PY = ROOT / ".venv" / "bin" / "python"

PAGES = {"overview": "views/overview.py", "valuation": "views/valuation.py",
         "sentiment": "views/sentiment.py", "backtester": "views/backtester.py",
         "simulator": "views/simulator.py"}


def banner(text: str) -> None:
    print(f"\n{'=' * 68}\n  {text}\n{'=' * 68}")


def metrics(at) -> dict:
    return {m.label: m.value for m in at.metric}


def click(at, label: str):
    """Click a button by visible label - indexes shift as pages reveal controls."""
    for button in at.button:
        if button.label.strip() == label.strip():
            return button.click().run()
    raise KeyError(f"button {label!r} not found; have {[b.label for b in at.button]}")


# ═════════════════════════════════════════════════════════════════════════
# the app
# ═════════════════════════════════════════════════════════════════════════

def cmd_app(args) -> None:
    banner("ALPHALENS  (app.py)")
    if args.live:
        print(f"[app] LIVE - Yahoo Finance, ticker {args.ticker}")
    else:
        from alphalens.data import fixtures

        fixtures.install()
        print("[app] fixtures - AAPL prices, fundamentals and mock news")

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    if args.live:
        at.session_state["alphalens_ticker"] = args.ticker
    at.run()
    assert not at.exception, [e.value for e in at.exception]

    overview = metrics(at)
    assert [t.value for t in at.title] == ["AlphaLens"]
    for label in ("Last close", "Valuation signal", "News sentiment",
                  "MA 20/50 return", "RSI (14)"):
        assert label in overview, f"overview card missing {label!r}: {overview}"
    print("[ok] overview: " + " | ".join(f"{k} {v}" for k, v in overview.items()))

    banner("VALUATION")
    at.switch_page(PAGES["valuation"]).run()
    assert not at.exception, [e.value for e in at.exception]
    valuation = metrics(at)
    assert valuation["Signal"] == overview["Valuation signal"], \
        (valuation["Signal"], overview["Valuation signal"])
    print(f"[ok] page signal {valuation['Signal']} matches the overview card, "
          f"price {valuation['Market price']}")

    at.sidebar.slider(key="val_growth").set_value(35).run()
    at.sidebar.slider(key="val_wacc").set_value(7).run()
    optimistic = metrics(at)["Signal"]
    assert "BUY" in optimistic, optimistic
    print(f"[ok] growth 35% / WACC 7% flips the verdict to {optimistic}")
    at.sidebar.slider(key="val_growth").set_value(10).run()
    at.sidebar.slider(key="val_wacc").set_value(10).run()
    charts = len(at.get("plotly_chart"))
    assert charts >= 4, f"expected gauge, projections and sensitivity, got {charts}"
    print(f"[ok] {charts} charts incl. the sensitivity heatmap")

    banner("STRATEGY BACKTESTER")
    at.switch_page(PAGES["backtester"]).run()
    assert not at.exception, [e.value for e in at.exception]
    backtest = metrics(at)
    assert backtest["Total return"][:4] == overview["MA 20/50 return"][:4], \
        (backtest["Total return"], overview["MA 20/50 return"])
    print(f"[ok] MA 20/50: return {backtest['Total return']} sharpe {backtest['Sharpe']} "
          f"drawdown {backtest['Max drawdown']} trades {backtest['Trades']} "
          "(matches the overview card)")

    at.sidebar.selectbox(key="bt_strategy").select("macd").run()
    long_only = metrics(at)
    at.sidebar.toggle(key="bt_short").set_value(True).run()
    long_short = metrics(at)
    assert long_only["Total return"] != long_short["Total return"]
    print(f"[ok] MACD long-only {long_only['Total return']} (sharpe {long_only['Sharpe']}) "
          f"vs long/short {long_short['Total return']} (sharpe {long_short['Sharpe']})")
    at.sidebar.toggle(key="bt_short").set_value(False).run()

    at.sidebar.radio(key="bt_source").set_value("Sample data").run()
    print(f"[ok] sample CSV source: MACD return {metrics(at)['Total return']}")
    at.sidebar.radio(key="bt_source").set_value("Active ticker").run()

    at.sidebar.selectbox(key="bt_strategy").select(args.strategy).run()
    charts = len(at.get("plotly_chart"))
    handoff = [b.label for b in at.button if b.label.startswith("▶ Replay")]
    assert handoff, [b.label for b in at.button]
    click(at, handoff[0])
    # st.switch_page moves a browser, but AppTest stays put: navigate explicitly
    # so the simulator page actually renders and consumes the request.
    at.switch_page(PAGES["simulator"]).run()
    state = at.session_state["simulator"]
    assert not at.exception, [e.value for e in at.exception]
    assert state.loaded and state.strategy_key == args.strategy, \
        (state.loaded, state.strategy_key)
    print(f"[ok] handoff: simulator loaded {state.symbol} ({len(state.frame)} candles) "
          f"with {state.strategy_key}; backtester drew {charts} charts incl. the sweep")

    banner("TRADING SIMULATOR")
    at.sidebar.radio(key="sim_strategy").set_value("manual").run()
    start = at.session_state["simulator"].index

    click(at, "BUY")
    state = at.session_state["simulator"]
    assert state.engine.holdings > 0, state.engine.holdings
    print(f"[ok] BUY  -> long {state.engine.holdings} @ {state.price:,.2f}")

    for _ in range(3):
        click(at, "⏭")
    state = at.session_state["simulator"]
    assert state.index == start + 3, (state.index, start)
    print(f"[ok] stepped 3 candles {start} -> {state.index}")

    click(at, "SELL")
    state = at.session_state["simulator"]
    assert state.engine.holdings == 0
    print(f"[ok] SELL -> flat, realised {state.engine.realized_pnl:+,.2f}")

    click(at, "SELL")
    state = at.session_state["simulator"]
    assert state.engine.holdings < 0
    print(f"[ok] SELL -> short {state.engine.holdings} "
          f"(flip recorded as {[t.action for t in state.engine.trades]})")

    click(at, "Reset portfolio")
    from alphalens.signals.strategies import get
    from alphalens.trading import performance

    # Switch strategy through the sidebar, as a user would: the page recomputes
    # the signals on that rerun. Calling into the page module directly would
    # touch a session state that only exists inside a script run.
    at.sidebar.radio(key="sim_strategy").set_value(args.strategy).run()
    state = at.session_state["simulator"]
    assert state.signals is not None, "no signals after choosing a strategy"

    # The replay fragment cannot tick under AppTest, so drive the same calls it
    # makes. The buttons above already prove the manual controls work.
    fired = 0
    for index in range(state.index, min(state.index + args.candles, len(state.frame))):
        state.index = index
        signal = state.signal_at(index)
        if signal in ("BUY", "SELL"):
            state.engine.execute(signal, state.price, state.timestamp, get(args.strategy).name)
            fired += 1
        state.engine.record_value(state.timestamp, state.price)
    at.run()
    engine = at.session_state["simulator"].engine
    print(f"[ok] replayed {args.candles} candles on {get(args.strategy).name}: "
          f"{fired} signals executed, {len(engine.trades)} trades, "
          f"realised {engine.realized_pnl:+,.2f}")
    stats = performance.summarise(engine.trades, engine.equity_curve, engine.initial_capital)
    print("     " + " · ".join(
        f"{key} {stats[key]:.2f}" for key in
        ("total_return", "win_rate", "max_drawdown", "sharpe_ratio")))
    simulator_trades = len(engine.trades)

    banner("NEWS SENTIMENT")
    at.switch_page(PAGES["sentiment"]).run()
    assert not at.exception, [e.value for e in at.exception]
    sentiment = metrics(at)
    assert (sentiment["Score"], sentiment["Label"]) == ("-0.245", "Bearish"), sentiment
    print(f"[ok] ad hoc headline: {sentiment['Score']} {sentiment['Label']}")
    print(f"[ok] live news: {sentiment['Sentiment']} average {sentiment['Average score']} "
          f"momentum {sentiment['Momentum']} confidence {sentiment['Confidence']}")
    assert sentiment["Sentiment"] == overview["News sentiment"]
    if not args.live:
        assert (sentiment["Sentiment"], sentiment["Average score"]) == ("BULLISH", "+0.235")
        print("[ok] mock AAPL news scores exactly as the CLI scores AAPL (+0.235)")

    ticker = at.session_state["alphalens_ticker"]
    at.button_group(key=f"sentiment_source_{ticker}").set_value("Sample feed").run()
    table = at.dataframe[0].value
    assert len(table) == 5, table
    print(f"[ok] sample feed: {len(table)} tickers, drill-down on "
          f"{at.selectbox(key='sentiment_ticker').value}")
    at.selectbox(key="sentiment_ticker").select("BA").run()
    assert metrics(at)["Sentiment"] == "BEARISH"
    print("[ok] drill-down BA: BEARISH")

    banner("SHARED TICKER")
    loaded = at.session_state["simulator"].symbol
    target = "MSFT" if at.session_state["alphalens_ticker"] != "MSFT" else "NVDA"
    at.switch_page(PAGES["valuation"]).run()
    at.sidebar.selectbox(key="alphalens_ticker_picker").set_value(target).run()
    assert at.session_state["alphalens_ticker"] == target
    assert not at.exception, [e.value for e in at.exception]
    header = [m.value for m in at.markdown if f"`{target}`" in m.value]
    assert header, f"valuation did not follow the picker to {target}"
    print(f"[ok] picker -> {target}: valuation header {header[0].strip()!r}, "
          f"signal {metrics(at).get('Signal')}")

    at.switch_page(PAGES["simulator"]).run()
    stale = [c.value for c in at.sidebar.caption if "Showing" in c.value]
    assert stale and loaded in stale[0] and target in stale[0], stale
    state = at.session_state["simulator"]
    assert state.loaded and len(state.engine.trades) == simulator_trades
    print(f"[ok] simulator keeps its {loaded} session ({len(state.engine.trades)} trades) "
          f"and flags the change: {stale[0]!r}")

    at.switch_page(PAGES["overview"]).run()
    assert not at.exception, [e.value for e in at.exception]
    print(f"[ok] overview now on {target}: " +
          " | ".join(f"{k} {v}" for k, v in metrics(at).items()))
    print("\nAPP PASS")


# ═════════════════════════════════════════════════════════════════════════
# command lines, tests, package
# ═════════════════════════════════════════════════════════════════════════

def run(*command: str) -> str:
    result = subprocess.run([str(PY), *command], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[fail] {' '.join(command)} exited {result.returncode}\n"
              f"{result.stdout}\n{result.stderr}")
        sys.exit(result.returncode)
    return result.stdout


def cmd_cli(args) -> None:
    banner("COMMAND LINES")
    backtest = run("-m", "alphalens.backtest")
    print(backtest.rstrip())
    assert "$106,115.68" in backtest, "sample backtest figures changed"
    print("\n[ok] backtest CLI reproduces the sample-data figures")

    short = run("-m", "alphalens.backtest", "--strategy", "rsi", "--short")
    assert "RSI long/short" in short
    print("[ok] rsi --short: "
          + [line for line in short.splitlines() if "Total return" in line][0].strip())

    sentiment = run("-m", "alphalens.sentiment")
    assert "AAPL  BULLISH" in sentiment, sentiment[:400]
    print("[ok] sentiment CLI on the sample feed: " + ", ".join(
        line.split("(")[0].strip() for line in sentiment.splitlines()
        if any(label in line for label in ("BULLISH", "BEARISH", "NEUTRAL"))))

    one = run("-m", "alphalens.sentiment", "--text",
              "Nvidia beats estimates but warns of weak demand")
    assert one.startswith("-0.2449  bearish"), one
    print(f"[ok] sentiment --text: {one.splitlines()[0]}")

    payload = json.loads(run("-m", "alphalens.sentiment", "--json"))
    assert sorted(payload) == ["AAPL", "BA", "JPM", "NVDA", "TSLA"]
    print(f"[ok] sentiment --json: {len(payload)} tickers")
    print("\nCLI PASS")


def cmd_tests(args) -> None:
    banner("TESTS")
    if subprocess.run([str(PY), "-m", "pytest", "tests", "-q"], cwd=ROOT).returncode != 0:
        sys.exit(1)
    print("\nTESTS PASS")


def cmd_lab(args) -> None:
    banner("PACKAGE  (no Streamlit)")
    from alphalens.backtest import engine
    from alphalens.data import csv_prices, fixtures
    from alphalens.signals import indicators
    from alphalens.signals.strategies import Context, STRATEGIES, TRADEABLE, get
    from alphalens.trading.engine import PaperTradingEngine
    from alphalens.valuation.analysis import value

    frame = indicators.enrich(fixtures.price_frame())
    detections = Context.for_frame(frame)
    extra = [c for c in frame.columns if c not in ("open", "high", "low", "close", "volume")]
    print(f"[ok] indicators: {extra}")
    print(f"[ok] detections: {len(detections.fvg)} FVGs, {len(detections.sweeps)} sweeps")

    for key in TRADEABLE:
        signals = get(key).signals(frame, detections)
        result = engine.run_strategy(frame, get(key), symbol="AAPL", context=detections)
        counts = {k: int(v) for k, v in signals.value_counts().items()}
        print(f"  {STRATEGIES[key].name:<16} {counts} -> {result.total_return:+7.2%} "
              f"sharpe {result.sharpe:5.2f} trades {result.trades:3d}")

    sample, name = csv_prices.sample_prices()
    result = engine.run_strategy(sample, get("ma_crossover"), symbol=name, capital=10_000)
    assert round(result.final_equity, 2) == 10_611.57, result.final_equity
    print(f"[ok] sample MA 20/50 final equity ${result.final_equity:,.2f} (unchanged)")

    account = PaperTradingEngine(100_000, "INR")
    account.buy(100.0, frame.index[0], quantity=10)
    flip = account.sell(120.0, frame.index[1], quantity=20)
    assert "₹" in flip["message"], flip["message"]
    print(f"[ok] paper engine in INR: {flip['message']}")

    verdict = value(fixtures.fundamentals()).verdict
    print(f"[ok] valuation: {verdict.label} fair value ${verdict.fair_value:,.2f} "
          f"vs price ${verdict.current_price:,.2f}")
    print("\nLAB PASS")


def cmd_all(args) -> None:
    """Each stage in its own process, so one failure is visible on its own."""
    failures = 0
    for stage in ("tests", "cli", "lab", "app"):
        command = [str(PY), str(Path(__file__).resolve()), stage]
        if args.live and stage == "app":
            command.append("--live")
        if subprocess.run(command).returncode != 0:
            print(f"\n*** {stage} FAILED ***")
            failures += 1
    print("\n" + "=" * 68)
    print("  ALL PASS" if not failures else f"  {failures} STAGE(S) FAILED")
    print("=" * 68)
    sys.exit(1 if failures else 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true",
                        help="use Yahoo Finance instead of the fixtures")
    parser.add_argument("--ticker", default="AAPL")
    subcommands = parser.add_subparsers(dest="command", required=True)

    app = subcommands.add_parser("app")
    app.add_argument("--strategy", default="rsi")
    app.add_argument("--candles", type=int, default=300)
    app.set_defaults(run=cmd_app)

    subcommands.add_parser("cli").set_defaults(run=cmd_cli)
    subcommands.add_parser("tests").set_defaults(run=cmd_tests)
    subcommands.add_parser("lab").set_defaults(run=cmd_lab)
    subcommands.add_parser("all").set_defaults(run=cmd_all)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
