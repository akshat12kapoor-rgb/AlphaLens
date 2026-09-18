#!/usr/bin/env python
"""
Screenshot an AlphaLens Streamlit surface.

Starts serve.py on a free port, drives the page with Playwright/Chromium,
and writes PNGs to .claude/skills/run-alphalens/shots/.

    .venv/bin/python .claude/skills/run-alphalens/shot.py sim
    .venv/bin/python .claude/skills/run-alphalens/shot.py val
    .venv/bin/python .claude/skills/run-alphalens/shot.py both
    .venv/bin/python .claude/skills/run-alphalens/shot.py platform

`platform` walks AlphaOS: overview -> valuation -> news sentiment -> backtester
-> "Replay in Trading Simulator" handoff (asserts it lands with data loaded,
then that pressing play advances the replay, which AppTest cannot do) -> away
and back (asserts state survived) -> sidebar ticker picker to MSFT (asserts the
simulator flags stale data and valuation follows).

Streamlit renders over a websocket, so the DOM is empty for a beat after load.
We wait on real content (a metric / the chart canvas), never a fixed sleep.
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent
ROOT = SKILL.parents[2]
SHOTS = SKILL / "shots"
PY = ROOT / ".venv" / "bin" / "python"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_health(port: int, proc: subprocess.Popen, timeout: int = 90) -> None:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server died:\n{proc.stdout.read() if proc.stdout else ''}")
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2) as r:
                if r.read().decode().strip() == "ok":
                    return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"server not healthy on {port} within {timeout}s")


def _candle(pg) -> int:
    """Replay position from the simulator header badge, e.g. '25 Nov 2024 · 51 / 500'."""
    import re
    m = re.search(r"· (\d+) / (\d+)", pg.inner_text("body"))
    if not m:
        raise AssertionError("simulator header badge not found")
    return int(m.group(1))


NAV_PATHS = {"Trading Simulator": "simulator", "Valuation": "valuation",
             "News Sentiment": "sentiment", "Strategy Backtester": "backtester"}


def _nav(pg, title: str) -> None:
    # Click the sidebar link: it keeps the session, a full URL load starts a new
    # one. Select by href - Material icons render as ligature text, so the link's
    # accessible name is "candlestick_chart Trading Simulator", not the title.
    pg.locator(f'[data-testid="stSidebarNavLink"][href$="/{NAV_PATHS[title]}"]').click()


def walk_platform(pg) -> list[Path]:
    """AlphaOS end to end in a real browser."""
    out: list[Path] = []

    def snap(name: str) -> None:
        f = SHOTS / name
        pg.screenshot(path=str(f), full_page=False)
        out.append(f)

    pg.wait_for_selector("text=trading simulation platform", timeout=120_000)
    pg.wait_for_selector("text=Valuation signal", timeout=120_000)
    pg.wait_for_selector(".js-plotly-plot", timeout=60_000)
    pg.wait_for_timeout(1500)
    snap("alphaos-overview.png")

    _nav(pg, "Valuation")
    pg.wait_for_selector("text=Key Financial Metrics", timeout=120_000)
    pg.wait_for_selector(".js-plotly-plot", timeout=60_000)
    pg.wait_for_timeout(2000)
    snap("alphaos-valuation.png")

    _nav(pg, "News Sentiment")
    pg.wait_for_selector("text=in the news", timeout=60_000)
    pg.wait_for_selector(".js-plotly-plot", timeout=60_000)
    pg.wait_for_timeout(1500)
    snap("alphaos-sentiment.png")

    _nav(pg, "Strategy Backtester")
    pg.wait_for_selector("text=Parameter sweep", timeout=120_000)
    pg.wait_for_selector(".js-plotly-plot", timeout=60_000)
    pg.wait_for_timeout(2000)
    snap("alphaos-backtester.png")

    # Backtest -> simulator handoff: lands on the simulator with data loaded.
    pg.get_by_role("button", name="Trading Simulator").filter(has_text="Replay").click()
    pg.wait_for_selector("text=Loaded 500 candles", timeout=120_000)
    pg.wait_for_selector(".js-plotly-plot", timeout=60_000)
    pg.wait_for_timeout(1500)
    if "/simulator" not in pg.url:
        raise AssertionError(f"handoff did not navigate to the simulator ({pg.url})")
    print(f"[shot] handoff landed on {pg.url.rsplit('/', 1)[-1]} with data loaded")
    before = _candle(pg)
    pg.get_by_role("button", name="▶", exact=True).click()
    pg.wait_for_timeout(4000)
    snap("alphaos-simulator-playing.png")
    # The replay fragment redraws only the chart; the header badge is outside it
    # and refreshes on the full rerun that pausing triggers.
    pg.get_by_role("button", name="⏸", exact=True).click()
    pg.wait_for_timeout(2000)
    paused = _candle(pg)
    print(f"[shot] replay fragment in browser: candle {before} -> {paused} after ~4s of play")
    if paused <= before:
        raise AssertionError(f"play did not advance the replay ({before} -> {paused})")
    snap("alphaos-simulator.png")

    _nav(pg, "News Sentiment")
    pg.wait_for_selector("text=in the news", timeout=60_000)
    _nav(pg, "Trading Simulator")
    pg.wait_for_selector(".js-plotly-plot", timeout=90_000)
    pg.wait_for_timeout(1500)
    back = _candle(pg)
    print(f"[shot] back on simulator: candle {back} (paused at {paused})")
    if back != paused:
        raise AssertionError(f"simulator state lost across pages ({paused} -> {back})")

    # Shared ticker: type a new symbol into the sidebar picker.
    picker = pg.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first
    picker.click()
    pg.keyboard.type("MSFT")
    pg.keyboard.press("Enter")
    pg.wait_for_selector("text=Fetch Data to load", timeout=60_000)
    print("[shot] picker -> MSFT: simulator flags its loaded AAPL data as stale")
    _nav(pg, "Valuation")
    pg.wait_for_selector("text=Valuing", timeout=60_000)
    pg.wait_for_function("() => document.body.innerText.includes('Valuing MSFT')", timeout=60_000)
    print("[shot] valuation follows the picker: 'Valuing MSFT'")
    return out


def capture(app: str, live: bool) -> list[Path]:
    SHOTS.mkdir(exist_ok=True)
    port = free_port()
    cmd = [str(PY), str(SKILL / "serve.py"), app, "--port", str(port)]
    if live:
        cmd.append("--live")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out: list[Path] = []
    try:
        wait_health(port, proc)
        print(f"[shot] {app} healthy on {port}")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            pg.goto(f"http://localhost:{port}", wait_until="domcontentloaded")

            if app == "platform":
                out += walk_platform(pg)
            elif app == "sim":
                # landing state: sidebar loaded, no data yet
                pg.wait_for_selector("text=Fetch Data", timeout=60_000)
                pg.wait_for_timeout(1500)
                f = SHOTS / "sim-landing.png"
                pg.screenshot(path=str(f), full_page=False); out.append(f)

                pg.get_by_text("Fetch Data").first.click()
                # chart only exists once data is loaded
                pg.wait_for_selector(".js-plotly-plot", timeout=90_000)
                pg.wait_for_timeout(2500)
                f = SHOTS / "sim-loaded.png"
                pg.screenshot(path=str(f), full_page=False); out.append(f)

                # step a few candles so the shot shows a moved playhead
                for _ in range(3):
                    pg.get_by_text("⏭+1").first.click()
                    pg.wait_for_timeout(700)
                f = SHOTS / "sim-stepped.png"
                pg.screenshot(path=str(f), full_page=False); out.append(f)
            else:
                pg.wait_for_selector('[data-testid="stMetric"]', timeout=90_000)
                pg.wait_for_selector(".js-plotly-plot", timeout=90_000)
                pg.wait_for_timeout(2500)
                f = SHOTS / "val-dashboard.png"
                pg.screenshot(path=str(f), full_page=False); out.append(f)
                f = SHOTS / "val-fullpage.png"
                pg.screenshot(path=str(f), full_page=True); out.append(f)

            b.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("app", choices=["sim", "val", "both", "platform"])
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    targets = ["sim", "val"] if a.app == "both" else [a.app]
    made: list[Path] = []
    for t in targets:
        made += capture(t, a.live)

    print("\n[shot] wrote:")
    for f in made:
        print(f"  {f.relative_to(ROOT)}  ({f.stat().st_size // 1024} KB)")
    if not made:
        sys.exit(1)


if __name__ == "__main__":
    main()
