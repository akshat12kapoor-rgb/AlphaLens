#!/usr/bin/env python
"""
Launch one AlphaLens Streamlit surface as a REAL server, optionally with the
offline fixture wired in so the page renders loaded data with no network.

    .venv/bin/python .claude/skills/run-alphalens/serve.py sim [--port 8501] [--live]
    .venv/bin/python .claude/skills/run-alphalens/serve.py val [--port 8502] [--live]

Used on its own to eyeball the app in a browser, and by shot.py to take
screenshots. Ctrl-C to stop.

Both apps default to port 8501 - run them on different ports or one at a time.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent
ROOT = SKILL.parents[2]
FIX = SKILL / "fixtures"
APPS = {"sim": ROOT / "stock_simulator", "val": ROOT / "stock-valuation-dashboard"}


def patch_sim() -> None:
    import pandas as pd
    import modules.data_fetcher as dfm
    df = pd.read_csv(FIX / "AAPL_1d.csv", index_col=0, parse_dates=True)
    dfm.fetch_data = lambda *a, **k: df.copy()


def patch_val() -> None:
    import pandas as pd
    import modules.data_fetcher as dfm
    raw = json.load(open(FIX / "AAPL_fundamentals.json"))
    data = {k: (pd.Series(v["__series__"], dtype="float64")
                if isinstance(v, dict) and "__series__" in v else v)
            for k, v in raw.items()}
    dfm.fetch_stock_data = lambda t: dict(data, ticker=t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("app", choices=list(APPS))
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--live", action="store_true", help="real Yahoo data, no fixture")
    a = ap.parse_args()

    unit = APPS[a.app]
    # Exactly one component on sys.path: both ship a top-level `modules` package.
    sys.path.insert(0, str(unit))

    if not a.live:
        (patch_sim if a.app == "sim" else patch_val)()
        print(f"[serve] {a.app}: fixture wired in (offline)", flush=True)

    from streamlit import config
    from streamlit.web import bootstrap

    config.set_option("server.port", a.port, "flag")
    config.set_option("server.headless", True, "flag")
    config.set_option("browser.gatherUsageStats", False, "flag")
    config.set_option("server.fileWatcherType", "none", "flag")

    print(f"[serve] http://localhost:{a.port}  ({unit.name}/app.py)", flush=True)
    bootstrap.run(str(unit / "app.py"), False, [], {})


if __name__ == "__main__":
    main()
