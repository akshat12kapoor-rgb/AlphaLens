#!/usr/bin/env python
"""
Screenshot an AlphaLens Streamlit surface.

Starts serve.py on a free port, drives the page with Playwright/Chromium,
and writes PNGs to .claude/skills/run-alphalens/shots/.

    .venv/bin/python .claude/skills/run-alphalens/shot.py sim
    .venv/bin/python .claude/skills/run-alphalens/shot.py val
    .venv/bin/python .claude/skills/run-alphalens/shot.py both

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

            if app == "sim":
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
    ap.add_argument("app", choices=["sim", "val", "both"])
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
