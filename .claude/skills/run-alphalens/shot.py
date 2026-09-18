#!/usr/bin/env python
"""
Screenshot AlphaLens, and check what AppTest cannot.

    .venv/bin/python .claude/skills/run-alphalens/shot.py

Starts serve.py on a free port, drives Chromium with Playwright and writes PNGs
to .claude/skills/run-alphalens/shots/. Along the way it asserts the things that
only exist in a browser: pressing play advances the replay, the backtester's
handoff navigates to a loaded simulator, and the sidebar ticker picker moves
every page.

Streamlit paints over a websocket, so every wait is on real content appearing,
never a fixed sleep.
"""
from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent
ROOT = SKILL.parents[2]
SHOTS = SKILL / "shots"
PY = ROOT / ".venv" / "bin" / "python"

NAV = {"Overview": "overview", "Valuation": "valuation", "News Sentiment": "sentiment",
       "Strategy Backtester": "backtester", "Trading Simulator": "simulator"}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_healthy(port: int, process: subprocess.Popen, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server died:\n{process.stdout.read() if process.stdout else ''}")
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2) as r:
                if r.read().decode().strip() == "ok":
                    return
        except Exception:  # noqa: BLE001 - the server is simply not up yet
            time.sleep(0.5)
    raise TimeoutError(f"server not healthy on {port} within {timeout}s")


def navigate(page, title: str) -> None:
    """Click the sidebar link. Material icons are part of the link's accessible
    name ("calculate Valuation"), so select by href; and clicking keeps the
    session, where loading a URL would start a new one."""
    page.locator(f'[data-testid="stSidebarNavLink"][href$="/{NAV[title]}"]').click()


def candle(page) -> int:
    """The replay position from the simulator's caption."""
    match = re.search(r"Candle (\d+) of", page.inner_text("body"))
    if not match:
        raise AssertionError("simulator candle caption not found")
    return int(match.group(1))


def walk(page) -> list[Path]:
    shots: list[Path] = []

    def snap(name: str) -> None:
        path = SHOTS / name
        page.screenshot(path=str(path), full_page=False)
        shots.append(path)

    page.wait_for_selector("text=trading simulation platform", timeout=120_000)
    page.wait_for_selector("text=Valuation signal", timeout=120_000)
    page.wait_for_selector(".js-plotly-plot", timeout=60_000)
    page.wait_for_timeout(1500)
    snap("alphalens-overview.png")

    navigate(page, "Valuation")
    page.wait_for_selector("text=Sensitivity", timeout=120_000)
    page.wait_for_selector(".js-plotly-plot", timeout=60_000)
    page.wait_for_timeout(2000)
    snap("alphalens-valuation.png")

    navigate(page, "News Sentiment")
    page.wait_for_selector("text=in the news", timeout=60_000)
    page.wait_for_selector(".js-plotly-plot", timeout=60_000)
    page.wait_for_timeout(1500)
    snap("alphalens-sentiment.png")

    navigate(page, "Strategy Backtester")
    page.wait_for_selector("text=Total return", timeout=120_000)
    page.wait_for_selector(".js-plotly-plot", timeout=60_000)
    page.wait_for_timeout(2000)
    snap("alphalens-backtester.png")

    page.get_by_role("button", name=re.compile("^▶ Replay")).click()
    page.wait_for_selector("text=Loaded", timeout=120_000)
    page.wait_for_selector(".js-plotly-plot", timeout=60_000)
    page.wait_for_timeout(1500)
    if "/simulator" not in page.url:
        raise AssertionError(f"handoff did not navigate to the simulator ({page.url})")
    print(f"[shot] handoff landed on {page.url.rsplit('/', 1)[-1]} with data loaded")

    before = candle(page)
    page.get_by_role("button", name="▶", exact=True).click()
    page.get_by_role("button", name="⏸", exact=True).wait_for(timeout=30_000)
    page.wait_for_timeout(4000)
    snap("alphalens-simulator-playing.png")
    page.get_by_role("button", name="⏸", exact=True).click()
    page.wait_for_timeout(2000)
    paused = candle(page)
    print(f"[shot] replay fragment in browser: candle {before} -> {paused} after ~4s of play")
    if paused <= before:
        raise AssertionError(f"play did not advance the replay ({before} -> {paused})")
    snap("alphalens-simulator.png")

    navigate(page, "News Sentiment")
    page.wait_for_selector("text=in the news", timeout=60_000)
    navigate(page, "Trading Simulator")
    page.wait_for_selector(".js-plotly-plot", timeout=90_000)
    page.wait_for_timeout(1500)
    if candle(page) != paused:
        raise AssertionError(f"simulator state lost across pages ({paused} -> {candle(page)})")
    print(f"[shot] back on the simulator: still paused on candle {paused}")

    picker = page.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first
    picker.click()
    page.keyboard.type("MSFT")
    page.keyboard.press("Enter")
    page.wait_for_selector("text=Load data to switch", timeout=60_000)
    print("[shot] picker -> MSFT: the simulator flags its loaded data as stale")
    navigate(page, "Valuation")
    # The header renders the symbol as a code span, so match the heading itself
    # rather than backticks in the page text (and not the picker in the sidebar).
    page.wait_for_selector(":is(h1,h2,h3):has-text('MSFT')", timeout=60_000)
    print("[shot] valuation follows the picker to MSFT")
    return shots


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    SHOTS.mkdir(exist_ok=True)
    port = free_port()
    command = [str(PY), str(SKILL / "serve.py"), "--port", str(port)]
    if args.live:
        command.append("--live")
    server = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_healthy(port, server)
        print(f"[shot] healthy on {port}")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(f"http://localhost:{port}", wait_until="domcontentloaded")
            shots = walk(page)
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    print("\n[shot] wrote:")
    for path in shots:
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size // 1024} KB)")
    if not shots:
        sys.exit(1)


if __name__ == "__main__":
    main()
