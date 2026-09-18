#!/usr/bin/env python
"""
Run AlphaOS as a real server, with the offline fixtures wired in.

    .venv/bin/python .claude/skills/run-alphalens/serve.py            # port 8501
    .venv/bin/python .claude/skills/run-alphalens/serve.py --port 8600
    .venv/bin/python .claude/skills/run-alphalens/serve.py --live     # real Yahoo data

Used to eyeball the app without a network, and by shot.py for screenshots.
Ctrl-C to stop.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--live", action="store_true", help="real Yahoo data, no fixtures")
    args = parser.parse_args()

    # Run from the repo root so Streamlit reads .streamlit/config.toml and the
    # views/ page paths resolve.
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    if not args.live:
        from alphalens.data import fixtures

        fixtures.install()
        print("[serve] fixtures wired in: prices, fundamentals and mock news", flush=True)

    from streamlit import config
    from streamlit.web import bootstrap

    config.set_option("server.port", args.port, "flag")
    config.set_option("server.headless", True, "flag")
    config.set_option("browser.gatherUsageStats", False, "flag")
    config.set_option("server.fileWatcherType", "none", "flag")

    print(f"[serve] http://localhost:{args.port}", flush=True)
    bootstrap.run(str(ROOT / "app.py"), False, [], {})


if __name__ == "__main__":
    main()
