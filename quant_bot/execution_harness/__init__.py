"""Single, versioned execution harness (owner: execution-sim agent).

See docs/agents/harness/HARNESS.md for the specification and version log.
Any behaviour change = new VERSION + HARNESS.md entry + Validator review.
"""
VERSION = "1.3.0"

from .costs import (PLATFORMS, TABLE_PLATFORMS, USD_PER_CAD, PlatformCosts, Sourced, get_platform,  # noqa: E402
                    with_per_share_fee)
from .fills import ExitRule, simulate_trade  # noqa: E402
from .harness import apply_costs, profit_factor, run_trades, simulate_account, summarize  # noqa: E402
from .data import load_bars  # noqa: E402

__all__ = ["VERSION", "PLATFORMS", "TABLE_PLATFORMS", "USD_PER_CAD", "PlatformCosts", "Sourced", "get_platform", "ExitRule",
           "simulate_trade", "run_trades", "apply_costs", "summarize", "simulate_account", "profit_factor",
           "load_bars", "with_per_share_fee"]
