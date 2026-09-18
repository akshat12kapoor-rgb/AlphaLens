"""Platform-wide defaults. Anything a user can change lives in the UI."""
from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
SAMPLES = PACKAGE_ROOT / "data" / "samples"
FIXTURES = REPO_ROOT / "fixtures"

#: Bars per year, for annualising returns and volatility.
TRADING_DAYS = 252

#: Paper-trading starting capital.
INITIAL_CAPITAL = 100_000.0
#: Fraction of cash deployed when a trade doesn't name a quantity.
DEFAULT_TRADE_FRACTION = 0.10

#: Backtest cost per unit of turnover (5 bps of traded notional).
DEFAULT_COMMISSION = 0.0005

#: Band around fair value inside which the valuation verdict is HOLD.
MARGIN_OF_SAFETY = 0.15
#: Weight given to the DCF when blending it with the multiples valuation.
DEFAULT_DCF_WEIGHT = 0.60

#: How long cached market data stays fresh, in seconds.
CACHE_TTL = 15 * 60

DEFAULT_TICKER = "AAPL"
