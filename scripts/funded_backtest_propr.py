"""Chronological Propr Classic 2-Step backtest of the frozen crypto baseline.

Same simulator and parameters as the live shadow on the remote
(paper_trading_bot/scripts/funded_shadow_crypto.py): risk per trade,
-3 %/day kill switch, Propr fee 0.075 %/side + half-spread + slippage, Propr
rules (step 1 +5 %, step 2 +10 %, daily loss 5 % of start-of-day balance on
equity, drawdown = HWM - 8 % trailing up to the start balance). Challenges are
run back to back in time: a breach starts a new paid attempt at the next
trade; a funded account is paid out monthly (80 % of the profit above start,
then the high-water mark resets, as a Propr payout does).

Trades: walk-forward TEST trades of the 9-symbol baseline
(docs/multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv), with each
trade's minute close path (clipped at its stop) for open-PnL marking.
Spreads: medians logged from Hyperliquid on 2026-10-04; x3 as a stress,
since 2021-2023 books were thinner. Funding is not modelled (trades last
<= 50 min, so at most one 8 h settlement can fall inside a trade).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paper_trading_bot" / "scripts"))
import funded_shadow_crypto as fs  # noqa: E402

LEDGER = ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv"
OUT = ROOT / "docs" / "funded_backtest_propr.csv"
SPREAD_BPS = {"BTC": 0.12, "ETH": 0.37, "SOL": 0.82, "XRP": 0.66, "DOGE": 1.14,
              "ADA": 1.52, "LINK": 0.70, "LTC": 0.99, "BNB": 0.38}  # logged 2026-10-04
FEE_USD = 50.0          # Classic 2-Step 5K challenge, non-refundable
ACCOUNT_USD = 5_000.0
PROFIT_SPLIT = 0.80


def load():
    raw = pd.read_csv(LEDGER, parse_dates=["entry_time", "exit_time"]).sort_values("entry_time").reset_index(drop=True)
    trades = pd.DataFrame({
        "signal_id": [f"t{i}" for i in range(len(raw))], "symbol": raw.symbol,
        "entry_time": raw.entry_time, "exit_time": raw.exit_time,
        "mid_price": 1.0, "exit_mid": 1.0 + raw.raw_return, "stop_distance": raw.stop_distance,
        "funding_rate": 0.0, "exit_reason": np.where(raw.was_stopped, "stop", "time")})
    marks = {}
    for sym, g in raw.groupby("symbol"):
        times, values = [], []
        for r in g.itertuples():
            path = np.array([float(x) for x in str(r.close_path).split(";") if x != ""])
            held = int((r.exit_time - r.entry_time).total_seconds() // 60)
            path = np.maximum(path[: held + 1], -r.stop_distance)
            times.extend(r.entry_time + pd.Timedelta(minutes=k) for k in range(len(path)))
            values.extend(1.0 + path)
        marks[sym] = pd.Series(values, index=pd.DatetimeIndex(times)).sort_index()
    return trades, marks


def run(trades, marks, risk, kill, spread_mult):
    lookup = lambda coin, ts: (SPREAD_BPS[coin] * spread_mult, "logged_median")  # noqa: E731
    attempts, ledger, current = fs.simulate(trades, marks, lookup, risk=risk, kill=kill,
                                            now=trades.exit_time.max(), payout_every=pd.Timedelta(days=30))
    passed1 = sum(any(p["phase"] == "STEP_1" for p in a.phases_passed) for a in attempts)
    funded = [a for a in attempts if any(p["phase"] == "STEP_2" for p in a.phases_passed)]
    payouts = [p for a in attempts for p in a.payouts]
    paid_usd = sum(p["profit_pct"] / 100 * ACCOUNT_USD * PROFIT_SPLIT for p in payouts)
    fees_usd = FEE_USD * len(attempts)
    first_funded = min((pd.Timestamp(next(p["at"] for p in a.phases_passed if p["phase"] == "STEP_2")) for a in funded), default=None)
    start = pd.Timestamp(attempts[0].started) if attempts else None
    return {"risk_pct": 100 * risk, "kill_pct": 100 * kill, "spread_x": spread_mult,
            "attempts_paid": len(attempts),
            "failed": sum(a.status == "FAILED" for a in attempts),
            "fail_reasons": pd.Series([a.reason for a in attempts if a.reason]).value_counts().to_dict(),
            "passed_step1": passed1, "reached_funded": len(funded),
            "days_to_first_funded": (first_funded - start).days if first_funded is not None else None,
            "payouts": len(payouts), "paid_to_trader_usd": round(paid_usd, 0),
            "challenge_fees_usd": fees_usd, "net_usd": round(paid_usd - fees_usd, 0),
            "end_state": current.get("phase"), "end_status": current.get("status"),
            "attempt_log": [(a.number, a.started[:10], (a.ended or "")[:10], a.status, a.reason,
                             [p["phase"] for p in a.phases_passed], len(a.payouts)) for a in attempts]}


def main():
    trades, marks = load()
    print(f"trades {len(trades)}  {trades.entry_time.min().date()} -> {trades.exit_time.max().date()}")
    rows = []
    for risk, spread in [(0.0035, 1), (0.0035, 3), (0.0025, 1), (0.005, 1)]:
        r = run(trades, marks, risk, 0.03, spread)
        rows.append(r)
        print({k: v for k, v in r.items() if k != "attempt_log"}, flush=True)
        for line in r["attempt_log"]:
            print("   ", line)
    pd.DataFrame([{k: v for k, v in r.items() if k != "attempt_log"} for r in rows]).to_csv(OUT, index=False)


if __name__ == "__main__":
    main()
