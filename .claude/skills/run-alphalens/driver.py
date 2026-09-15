#!/usr/bin/env python
"""
AlphaLens driver - launches and drives all three surfaces of the platform.

Run from the platform root (AlphaLens/):

    .venv/bin/python .claude/skills/run-alphalens/driver.py all

Commands:
    sim      [--strategy S] [--candles N]   simulator: fetch, trade, replay
    val      [--growth G] [--wacc W]        valuation: fetch, run models, read verdict
    sent                                    sentiment CLI + unit tests
    all                                     all three, each in its own process
    engine                                  direct invocation, no Streamlit (fast path)

Both Streamlit surfaces are driven headlessly through
streamlit.testing.v1.AppTest - it executes the real app.py, sets widgets,
clicks buttons and reads back st.session_state. No browser needed.
For a screenshot use shot.py instead.

Data comes from committed fixtures by default (offline, deterministic).
Pass --live to hit Yahoo Finance.

IMPORTANT: stock_simulator/ and stock-valuation-dashboard/ BOTH ship a
top-level package named `modules`. Only one can be imported per process.
That is why `all` re-execs this file as subprocesses instead of looping.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

SKILL = Path(__file__).resolve().parent
ROOT = SKILL.parents[2]                      # .../AlphaLens
SIM = ROOT / "stock_simulator"
VAL = ROOT / "stock-valuation-dashboard"
SENT = ROOT / "SentimentFinance"
FIX = SKILL / "fixtures"
PY = ROOT / ".venv" / "bin" / "python"


def use(component: Path) -> None:
    """Put exactly one component on sys.path. See the `modules` collision note."""
    sys.path.insert(0, str(component))


def banner(text: str) -> None:
    print(f"\n{'=' * 66}\n  {text}\n{'=' * 66}")


# ═════════════════════════════════════════════════════════════════════════
# simulator
# ═════════════════════════════════════════════════════════════════════════

def sim_fixture() -> int:
    import pandas as pd
    import modules.data_fetcher as dfm
    df = pd.read_csv(FIX / "AAPL_1d.csv", index_col=0, parse_dates=True)
    dfm.fetch_data = lambda *a, **k: df.copy()
    return len(df)


def click(at, label: str):
    """Click a button by visible label. Labels are the stable handle -
    positional indexes shift as the app reveals its replay controls."""
    t = label.strip()
    for b in at.button:
        if b.label.strip() == t:
            return b.click().run()
    raise KeyError(f"button {label!r} not found; have {[b.label for b in at.button]}")


def sim_boot(live: bool, ticker: str):
    from streamlit.testing.v1 import AppTest
    if live:
        print(f"[sim] LIVE - Yahoo Finance, ticker {ticker}")
    else:
        print(f"[sim] fixture - AAPL_1d.csv ({sim_fixture()} candles)")

    at = AppTest.from_file(str(SIM / "app.py"), default_timeout=180)
    at.run()
    if at.exception:
        for e in at.exception:
            print(e.value)
        sys.exit(1)

    if live:
        sb = at.sidebar.selectbox(key="ticker_select")
        match = next((o for o in sb.options if o.split()[0].upper() == ticker.upper()), None)
        if match:
            sb.select(match).run()

    click(at, "🔄  Fetch Data")
    # NOTE: session_state here is a SafeSessionState - it has no .get().
    # Use `key in state` / state[key].
    if not at.session_state["data_loaded"]:
        print("[sim] FAIL: data_loaded False after Fetch Data")
        for e in at.error:
            print("  ", e.value)
        sys.exit(1)
    return at


def cmd_sim(args) -> None:
    banner("SIMULATOR  (stock_simulator)")
    use(SIM)
    at = sim_boot(args.live, args.ticker)
    ss = at.session_state
    df = ss["df"]
    print(f"[ok] {len(df)} candles | {len(ss['fvg_df'])} FVGs | {len(ss['sweeps_df'])} sweeps")
    print(f"[ok] replay controls: {[b.label for b in at.button if b.label in ('⏮', '▶', '⏭+1')]}")

    start = ss["replay_idx"]
    px = lambda i: float(at.session_state["df"]["close"].iloc[i])

    # --- manual trade round trip, exercising the signed-holdings model ---
    click(at, "BUY")
    e = at.session_state["engine"]
    assert e.holdings > 0, f"expected long, got {e.holdings}"
    print(f"[ok] BUY  -> long {e.holdings} @ {px(start):,.2f}")

    for _ in range(3):
        click(at, "⏭+1")
    idx = at.session_state["replay_idx"]
    assert idx == start + 3, f"expected candle {start + 3}, got {idx}"
    print(f"[ok] stepped 3 candles {start} -> {idx}")

    click(at, "SELL")
    e = at.session_state["engine"]
    assert e.holdings == 0, f"expected flat, got {e.holdings}"
    print(f"[ok] SELL -> flat, realized {e.realized_pnl:+,.2f}")

    click(at, "SELL")
    e = at.session_state["engine"]
    assert e.holdings < 0, f"expected short, got {e.holdings}"
    print(f"[ok] SELL -> short {e.holdings} (flip = two Trade records)")
    for t in e.trade_history:
        print(f"       {t.action:<6}{t.quantity:>5} @ {t.price:>9,.2f}  pnl {t.pnl:>+9,.2f}")

    # --- auto-strategy replay -------------------------------------------
    # The replay loop is @st.fragment(run_every=0.25); AppTest cannot tick a
    # timer fragment, so we advance replay_idx and drive the same engine calls
    # the fragment makes.
    from modules.strategies import get_signals, STRATEGY_NAMES
    if args.strategy not in STRATEGY_NAMES:
        print(f"[sim] unknown strategy {args.strategy!r}, pick from {STRATEGY_NAMES}")
        sys.exit(2)

    click(at, "Reset Portfolio")
    ss = at.session_state
    ss["strategy"] = args.strategy
    ss["signals"] = get_signals(df, args.strategy,
                                fvg_df=ss["fvg_df"], sweeps_df=ss["sweeps_df"])
    at.run()

    engine = at.session_state["engine"]
    signals = at.session_state["signals"]
    i0 = at.session_state["replay_idx"]
    fired = 0
    for i in range(i0, min(i0 + args.candles, len(df))):
        s = signals.iloc[i]
        price, ts = float(df["close"].iloc[i]), df.index[i]
        if s == "BUY":
            engine.buy(price, ts, strategy=args.strategy); fired += 1
        elif s == "SELL":
            engine.sell(price, ts, strategy=args.strategy); fired += 1
        engine.record_portfolio_value(ts, price)
    end = min(i0 + args.candles, len(df) - 1)
    at.session_state["replay_idx"] = end
    at.run()

    last = float(df["close"].iloc[end])
    print(f"\n[ok] replayed {args.candles} candles on {args.strategy}: "
          f"{fired} signals executed")
    print(f"  holdings      {engine.holdings:+d}")
    print(f"  balance       {engine.balance:,.2f}")
    print(f"  realized P&L  {engine.realized_pnl:+,.2f}")
    print(f"  portfolio     {engine.get_portfolio_value(last):,.2f}")
    print(f"  trades        {len(engine.trade_history)}")

    # NOTE: takes (trade_history, portfolio_history, initial_capital) -
    # NOT the engine object.
    from modules.performance import calculate_performance_metrics
    perf = calculate_performance_metrics(
        engine.trade_history, engine.portfolio_history, engine.initial_capital)
    for k, v in perf.items():
        print(f"  {k:<20} {v}")
    print("\nSIM PASS")


# ═════════════════════════════════════════════════════════════════════════
# valuation
# ═════════════════════════════════════════════════════════════════════════

def val_fixture() -> str:
    import pandas as pd
    import modules.data_fetcher as dfm
    raw = json.load(open(FIX / "AAPL_fundamentals.json"))

    def restore(v):
        if isinstance(v, dict) and "__series__" in v:
            return pd.Series(v["__series__"], dtype="float64")
        return v

    data = {k: restore(v) for k, v in raw.items()}
    dfm.fetch_stock_data = lambda t: dict(data, ticker=t)
    return data["company_name"]


def cmd_val(args) -> None:
    banner("VALUATION  (stock-valuation-dashboard)")
    use(VAL)
    from streamlit.testing.v1 import AppTest

    if args.live:
        print(f"[val] LIVE - Yahoo Finance, ticker {args.ticker}")
    else:
        print(f"[val] fixture - AAPL_fundamentals.json ({val_fixture()})")

    at = AppTest.from_file(str(VAL / "app.py"), default_timeout=180)
    at.run()
    if at.exception:
        for e in at.exception:
            print(e.value)
        sys.exit(1)
    if at.error:
        for e in at.error:
            print("[val] app error:", e.value)
        sys.exit(1)

    def metrics():
        return {m.label: m.value for m in at.metric}

    m = metrics()
    print(f"[ok] app rendered {len(at.metric)} metrics")
    for k in ("Live Price", "Signal", "Revenue (TTM)", "Free Cash Flow", "EPS (TTM)"):
        if k in m:
            print(f"  {k:<20} {m[k]}")

    # --- move the assumptions and watch the verdict move ----------------
    def slider(label):
        for s in at.sidebar.slider:
            if s.label.strip() == label:
                return s
        raise KeyError(f"slider {label!r}; have {[s.label for s in at.sidebar.slider]}")

    base_signal = m.get("Signal")
    print(f"\n[ok] baseline signal: {base_signal}")

    slider("Stage 1 FCF Growth Rate").set_value(args.growth).run()
    slider("Discount Rate (WACC)").set_value(args.wacc).run()
    m2 = metrics()
    print(f"[ok] growth={args.growth}% wacc={args.wacc}% -> signal {m2.get('Signal')}")
    for k in ("Stage 1 PV", "PV of Terminal Val", "Intrinsic Value / Share"):
        if k in m2:
            print(f"  {k:<24} {m2[k]}")

    # extreme optimism should flip the verdict toward BUY
    slider("Stage 1 FCF Growth Rate").set_value(35).run()
    slider("Discount Rate (WACC)").set_value(7).run()
    m3 = metrics()
    print(f"[ok] growth=35% wacc=7%  -> signal {m3.get('Signal')}")
    assert m3.get("Signal") != m2.get("Signal") or "BUY" in str(m3.get("Signal")), \
        "verdict never moved - sliders may not be wired"

    click(at, "🚀 Analyse")
    print(f"[ok] Analyse re-run, signal {metrics().get('Signal')}")
    print("\nVAL PASS")


# ═════════════════════════════════════════════════════════════════════════
# sentiment
# ═════════════════════════════════════════════════════════════════════════

def cmd_sent(args) -> None:
    banner("SENTIMENT  (SentimentFinance)")
    print("[sent] stdlib only - no venv needed, runs on system python3")

    def run(*a):
        r = subprocess.run([sys.executable, *a], cwd=SENT,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[sent] FAIL rc={r.returncode}\n{r.stdout}\n{r.stderr}")
            sys.exit(1)
        return r.stdout

    out = run("analyze.py", "data/headlines.txt")
    print(out.rstrip()[:900])

    j = json.loads(run("analyze.py", "data/headlines.txt", "--json"))
    print(f"\n[ok] --json parsed: {len(j)} tickers {sorted(j)}")
    for t, v in sorted(j.items()):
        print(f"  {t:<6} {v['label']:<8} score={v['score']:+.4f} "
              f"conf={v['confidence']:<6} n={v['headline_count']}")

    one = run("analyze.py", "--text", "Nvidia beats estimates but warns of weak demand")
    print(f"\n[ok] --text ad hoc: {one.strip().splitlines()[0]}")
    assert "bearish" in one, "expected a bearish read on that mixed headline"

    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=SENT, capture_output=True, text=True)
    tail = r.stderr.strip().splitlines()[-1]
    print(f"[ok] unit tests: {tail}")
    if r.returncode != 0:
        sys.exit(1)
    print("\nSENT PASS")


# ═════════════════════════════════════════════════════════════════════════
# direct invocation - no Streamlit
# ═════════════════════════════════════════════════════════════════════════

def cmd_engine(args) -> None:
    """Fast path for PRs that touch module internals rather than the UI."""
    banner("DIRECT INVOCATION  (no Streamlit)")
    import pandas as pd
    use(SIM)
    from modules.indicators import calculate_all_indicators
    from modules.smc_detector import get_smc_analysis
    from modules.strategies import get_signals, STRATEGY_NAMES
    from modules.trading_engine import TradingEngine

    df = calculate_all_indicators(pd.read_csv(FIX / "AAPL_1d.csv", index_col=0, parse_dates=True))
    fvg, sweeps = get_smc_analysis(df)
    print(f"[ok] indicators {[c for c in df.columns if c not in list('a') and c not in ('open','high','low','close','volume')]}")
    print(f"[ok] {len(fvg)} FVGs, {len(sweeps)} sweeps")
    for s in STRATEGY_NAMES:
        print(f"  {s:<18} {get_signals(df, s, fvg_df=fvg, sweeps_df=sweeps).value_counts().to_dict()}")

    e = TradingEngine()
    e.buy(float(df['close'].iloc[100]), df.index[100])
    e.sell(float(df['close'].iloc[120]), df.index[120], quantity=e.holdings)
    e.sell(float(df['close'].iloc[120]), df.index[120])
    print(f"\n[ok] engine flip: holdings={e.holdings:+d} realized={e.realized_pnl:+,.2f} "
          f"trades={len(e.trade_history)}")
    print("\nENGINE PASS")


# ═════════════════════════════════════════════════════════════════════════

def cmd_all(args) -> None:
    """Each component gets its own process - see the `modules` collision note."""
    rc = 0
    for sub in ("sim", "val", "sent"):
        cmd = [str(PY), str(Path(__file__).resolve()), sub]
        if args.live:
            cmd.append("--live")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"\n*** {sub} FAILED (rc={r.returncode}) ***")
            rc = r.returncode
    print("\n" + "=" * 66)
    print("  ALL PASS" if rc == 0 else "  FAILURES ABOVE")
    print("=" * 66)
    sys.exit(rc)


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", help="hit Yahoo Finance instead of fixtures")
    p.add_argument("--ticker", default="AAPL")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sim")
    s.add_argument("--strategy", default="RSI Strategy")
    s.add_argument("--candles", type=int, default=300)
    s.set_defaults(fn=cmd_sim)

    v = sub.add_parser("val")
    v.add_argument("--growth", type=int, default=12, help="stage-1 FCF growth %%")
    v.add_argument("--wacc", type=int, default=9, help="discount rate %%")
    v.set_defaults(fn=cmd_val)

    sub.add_parser("sent").set_defaults(fn=cmd_sent)
    sub.add_parser("engine").set_defaults(fn=cmd_engine)
    sub.add_parser("all").set_defaults(fn=cmd_all)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
