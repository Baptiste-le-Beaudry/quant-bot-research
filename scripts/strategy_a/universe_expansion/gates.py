"""Pure preregistered decision gates for universe-expansion research."""
from __future__ import annotations


def solo_profitability(pf: float, expectancy: float, net_pnl: float) -> bool:
    return pf > 1.0 and expectancy > 0.0 and net_pnl > 0.0


def solo_decision(*, data_pass: bool, pf: float | None = None,
                  expectancy: float | None = None, net_pnl: float | None = None,
                  sample_quality: str | None = None) -> str:
    if not data_pass:
        return "DATA_REJECT"
    if pf is None or expectancy is None or net_pnl is None:
        raise ValueError("all TEST profitability metrics are required")
    if not solo_profitability(pf, expectancy, net_pnl):
        return "SOLO_REJECT"
    if sample_quality not in {"ADEQUATE_SAMPLE", "STRONG_SAMPLE"}:
        return "INSUFFICIENT_SAMPLE"
    return "PASS_SOLO"


def portfolio_allowed(solo_status: str) -> bool:
    return solo_status == "PASS_SOLO"

