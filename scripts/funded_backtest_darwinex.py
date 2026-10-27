"""Darwinex Zero backtest of the Equity paper bot's universe (2019-2024).

Same parameters as the live shadow (paper_trading_bot/scripts/
darwinex_shadow_equity.py): NORMAL sizing (0.5 % risk, 5 % open risk, 1.5x
gross) on the registered shared-capital portfolio engine, restricted to the
15 deployed symbols; each trade re-costed at USD 0.04/share/side commission,
0.02 % round-trip spread (assumed, Darwinex doesn't publish it) and a 6.5 %/yr
swap per night held. Darwinex Zero has no breach rule, so the account only
needs a track record; it then reports what DarwinIA pays on:
15 % of each quarter's gain on the allocated capital, above a high-water mark.
DarwinIA's allocation depends on a rating vs other traders that cannot be
reproduced here, so payouts are shown for fixed allocation scenarios.

Candidates: config D walk-forward TEST signals (pre-HOLDOUT), the same audited
candidate files the registered portfolio validation used.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant_bot.strategy_a_equity.portfolio import PortfolioLimits, simulate  # noqa: E402
from scripts.strategy_a_equity.run_portfolio_frontier import OUT as PORTFOLIO_OUT, Prices  # noqa: E402

SYMBOLS = ['ADBE', 'AMZN', 'AVGO', 'BA', 'BABA', 'COST', 'CRM', 'CSCO', 'MA', 'MCD', 'MU', 'PEP', 'QCOM', 'TXN', 'V']
COMMISSION, SPREAD_RT, SWAP = 0.04, 0.0002, 0.065
SUBSCRIPTION_USD_MONTH = 50.0
OUT = ROOT / "docs" / "funded_backtest_darwinex.csv"


def darwinex_ledger(model: str, prices: Prices) -> pd.DataFrame:
    cands = pd.read_pickle(PORTFOLIO_OUT / f"audited_candidates_{model}.pkl")
    cands = cands[cands.symbol.isin(SYMBOLS)]
    led, _, _ = simulate(cands, PortfolioLimits(0.005, 0.05, 1.5), prices)
    led = led.copy()
    et = led.entry_time.dt.tz_convert("America/New_York").dt.normalize()
    xt = led.exit_time.dt.tz_convert("America/New_York").dt.normalize()
    nights = (xt - et).dt.days.clip(lower=0)
    led["frac"] = led.notional / led.entry_equity
    cost = 2 * COMMISSION / led.entry_price + SPREAD_RT + nights * SWAP / 360
    led["r_darwinex"] = led.frac * (led.raw_return - cost)
    led["r_backtest"] = led.frac * (led.raw_return - 0.0002)
    return led.sort_values("exit_time")


def curve_stats(led: pd.DataFrame, col: str) -> dict:
    daily = led.groupby(led.exit_time.dt.tz_convert("UTC").dt.normalize())[col].sum()
    eq = (1 + daily).cumprod()
    years = (led.exit_time.max() - led.entry_time.min()).days / 365.25
    monthly = (1 + daily).groupby(daily.index.tz_localize(None).to_period("M")).prod() - 1
    quarterly = (1 + daily).groupby(daily.index.tz_localize(None).to_period("Q")).prod() - 1
    yearly = (1 + daily).groupby(daily.index.year).prod() - 1
    return {"cagr_pct": 100 * (eq.iloc[-1] ** (1 / years) - 1), "max_dd_pct": 100 * (eq / eq.cummax() - 1).min(),
            "monthly_var95_pct": -100 * np.percentile(monthly, 5),
            "positive_quarters_pct": 100 * (quarterly > 0).mean(),
            "yearly_pct": {int(k): round(100 * v, 1) for k, v in yearly.items()}, "quarterly": quarterly}


def darwinia_payout(quarterly: pd.Series, allocation: float, need_positive_6m: bool) -> float:
    """15 % of each quarter's gain on `allocation`, above a high-water mark.
    need_positive_6m: only allocated when the previous two quarters were net
    positive (a crude stand-in for DarwinIA's recent-return rating)."""
    paid, hwm, nav = 0.0, 1.0, 1.0
    q = quarterly.to_numpy()
    for i, r in enumerate(q):
        allocated = not need_positive_6m or (i >= 2 and (1 + q[i - 2]) * (1 + q[i - 1]) > 1)
        nav *= 1 + r
        if allocated and nav > hwm:
            paid += 0.15 * allocation * (nav - hwm)
        hwm = max(hwm, nav)
    return paid


def main() -> None:
    prices = Prices(SYMBOLS)
    rows = []
    for model in ("logistic", "rf"):
        cands = pd.read_pickle(PORTFOLIO_OUT / f"audited_candidates_{model}.pkl")
        prices.prepare(cands[cands.symbol.isin(SYMBOLS)].entry_time)
        led = darwinex_ledger(model, prices)
        years = (led.exit_time.max() - led.entry_time.min()).days / 365.25
        for col, label in (("r_backtest", "backtest costs (0.02%)"), ("r_darwinex", "Darwinex Zero costs")):
            s = curve_stats(led, col)
            row = {"model": model, "costs": label, "trades": len(led), "years": round(years, 1),
                   **{k: v for k, v in s.items() if k != "quarterly"}}
            if col == "r_darwinex":
                subs = SUBSCRIPTION_USD_MONTH * 12 * years
                for alloc in (30_000, 100_000):
                    for gated in (False, True):
                        paid = darwinia_payout(s["quarterly"], alloc, gated)
                        row[f"payout_{alloc // 1000}k_{'gated' if gated else 'always'}_usd"] = round(paid)
                        row[f"net_{alloc // 1000}k_{'gated' if gated else 'always'}_usd"] = round(paid - subs)
                row["subscription_usd"] = round(subs)
            rows.append(row)
            print(row, flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)


if __name__ == "__main__":
    main()
