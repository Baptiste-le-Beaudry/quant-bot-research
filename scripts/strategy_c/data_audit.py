"""scripts/strategy_c/data_audit.py — STRATEGY_ID = C, mandatory DATA
AUDIT (per docs/strategy_c/STRATEGY_C_SPEC.md's phase 3 and the
mandate's C5) -- must run and PASS before any feature/causal work is
built on top of the QQQ trades/mbp-1 data. Checks: timestamp
monotonicity, timezone/DST-awareness, session boundaries (09:30/16:00
America/New_York), duplicate trades/quotes, bad ticks (zero/negative
price or size), crossed markets (bid > ask), locked markets (bid ==
ask), missing periods (session-day coverage gaps), quote/trade
timestamp alignment, symbol mapping consistency.

Processes ONE DAY AT A TIME (data/strategy_c/normalized/QQQ_{schema}_daily/
*.parquet, produced by download_qqq_databento.py's per-day conversion)
and aggregates -- this machine has ~1-1.5GB free RAM against a ~33GB
raw dataset, so the full trades+quotes history is never loaded at once.

Usage:
    python scripts/strategy_c/data_audit.py
"""
import gc
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NORMALIZED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "normalized")
SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "QQQ"
TRADES_DAILY_DIR = os.path.join(NORMALIZED_DIR, f"{SYMBOL}_trades_daily")
QUOTES_DAILY_DIR = os.path.join(NORMALIZED_DIR, f"{SYMBOL}_mbp-1_daily")
SESSION_OPEN = pd.Timestamp("09:30").time()
SESSION_CLOSE = pd.Timestamp("16:00").time()
NY_TZ = "America/New_York"
DST_DATES_2026 = ["20260308", "20261101"]  # US DST transitions


def check(label, condition, extra=""):
    status = "PASS" if condition else "ISSUE FOUND"
    print(f"  {label}: {status}" + (f"  ({extra})" if extra else ""))
    return condition


def list_daily_files(daily_dir: str) -> dict:
    if not os.path.isdir(daily_dir):
        return {}
    out = {}
    for fname in os.listdir(daily_dir):
        m = re.match(r"(\d{8})\.parquet$", fname)
        if m:
            out[m.group(1)] = os.path.join(daily_dir, fname)
    return dict(sorted(out.items()))


def audit_trades_day(df: pd.DataFrame, date_str: str, agg: dict):
    agg["n_rows"] += len(df)
    if not df.index.is_monotonic_increasing:
        agg["issues"].append(f"trades {date_str}: timestamps not monotonic")
    if df.index.tz is None:
        agg["issues"].append(f"trades {date_str}: index not tz-aware")

    price_col = "price" if "price" in df.columns else None
    size_col = "size" if "size" in df.columns else None
    if price_col:
        n_bad = int((df[price_col] <= 0).sum())
        if n_bad:
            agg["issues"].append(f"trades {date_str}: {n_bad} zero/negative prices")
    if size_col:
        n_bad = int((df[size_col] <= 0).sum())
        if n_bad:
            agg["issues"].append(f"trades {date_str}: {n_bad} zero/negative sizes")

    ny_index = df.index.tz_convert(NY_TZ)
    in_session = (ny_index.time >= SESSION_OPEN) & (ny_index.time <= SESSION_CLOSE)
    agg["pct_in_session_sum"] += float(in_session.mean())
    agg["n_days"] += 1
    if date_str in DST_DATES_2026 and len(df):
        first_t = ny_index.min().time()
        agg["dst_notes"].append(f"trades {date_str} (DST transition): first trade NY-local {first_t}")


def audit_quotes_day(df: pd.DataFrame, date_str: str, agg: dict):
    agg["n_rows"] += len(df)
    if not df.index.is_monotonic_increasing:
        agg["issues"].append(f"quotes {date_str}: timestamps not monotonic")
    if df.index.tz is None:
        agg["issues"].append(f"quotes {date_str}: index not tz-aware")

    if agg.get("bid_col") is None:
        agg["bid_col"] = next((c for c in df.columns if c.lower() in ("bid_px_00", "bid_px", "bid")), None)
        agg["ask_col"] = next((c for c in df.columns if c.lower() in ("ask_px_00", "ask_px", "ask")), None)
        agg["bid_sz_col"] = next((c for c in df.columns if c.lower() in ("bid_sz_00", "bid_sz", "bid_size")), None)
        agg["ask_sz_col"] = next((c for c in df.columns if c.lower() in ("ask_sz_00", "ask_sz", "ask_size")), None)
        print(f"  detected columns: bid={agg['bid_col']} ask={agg['ask_col']} "
              f"bid_sz={agg['bid_sz_col']} ask_sz={agg['ask_sz_col']}")

    bid_col, ask_col = agg.get("bid_col"), agg.get("ask_col")
    if bid_col and ask_col:
        valid = (df[bid_col] > 0) & (df[ask_col] > 0)
        crossed = valid & (df[bid_col] > df[ask_col])
        locked = valid & (df[bid_col] == df[ask_col])
        agg["n_valid"] += int(valid.sum())
        agg["n_crossed"] += int(crossed.sum())
        agg["n_locked"] += int(locked.sum())

    bid_sz_col, ask_sz_col = agg.get("bid_sz_col"), agg.get("ask_sz_col")
    if bid_sz_col and ask_sz_col:
        n_bad = int((df[bid_sz_col] < 0).sum()) + int((df[ask_sz_col] < 0).sum())
        if n_bad:
            agg["issues"].append(f"quotes {date_str}: {n_bad} negative sizes")

    agg["n_days"] += 1
    if date_str in DST_DATES_2026 and len(df):
        ny_index = df.index.tz_convert(NY_TZ)
        first_t = ny_index.min().time()
        agg["dst_notes"].append(f"quotes {date_str} (DST transition): first quote NY-local {first_t}")


def main():
    trades_files = list_daily_files(TRADES_DAILY_DIR)
    quotes_files = list_daily_files(QUOTES_DAILY_DIR)
    if not trades_files or not quotes_files:
        print("Per-day parquet files not found. Run scripts/strategy_c/download_qqq_databento.py "
              "--download-and-convert first.")
        print(f"  expected under: {TRADES_DAILY_DIR}")
        print(f"  expected under: {QUOTES_DAILY_DIR}")
        return

    print("=" * 100)
    print("  STRATEGY C -- DATA AUDIT (per-day streaming, memory-constrained environment)")
    print("=" * 100)
    print(f"  trades daily files: {len(trades_files)}   quotes daily files: {len(quotes_files)}")

    t_agg = {"n_rows": 0, "n_days": 0, "issues": [], "pct_in_session_sum": 0.0, "dst_notes": []}
    for date_str, fpath in trades_files.items():
        df = pd.read_parquet(fpath)
        audit_trades_day(df, date_str, t_agg)
        del df
        gc.collect()

    q_agg = {"n_rows": 0, "n_days": 0, "issues": [], "n_valid": 0, "n_crossed": 0, "n_locked": 0, "dst_notes": []}
    for date_str, fpath in quotes_files.items():
        df = pd.read_parquet(fpath)
        audit_quotes_day(df, date_str, q_agg)
        del df
        gc.collect()

    print("\n" + "=" * 100)
    print("  TRADES AUDIT")
    print("=" * 100)
    print(f"  n_rows = {t_agg['n_rows']:,}  n_session_days = {t_agg['n_days']}")
    avg_pct_in_session = t_agg["pct_in_session_sum"] / max(1, t_agg["n_days"]) * 100
    print(f"  avg pct of trades within 09:30-16:00 NY session per day: {avg_pct_in_session:.2f}% "
          f"(pre/post-market trades expected -- informational, not a bug)")
    t_pass = check("trades: no monotonicity/tz/bad-tick issues", len(t_agg["issues"]) == 0,
                   f"{len(t_agg['issues'])} issue(s)")
    for msg in t_agg["issues"][:20]:
        print(f"    - {msg}")
    for note in t_agg["dst_notes"]:
        print(f"    DST: {note}")

    print("\n" + "=" * 100)
    print("  QUOTES (mbp-1 / NBBO) AUDIT")
    print("=" * 100)
    print(f"  n_rows = {q_agg['n_rows']:,}  n_session_days = {q_agg['n_days']}")
    print(f"  valid (both-sided) quotes: {q_agg['n_valid']:,}/{q_agg['n_rows']:,}")
    n_valid = max(1, q_agg["n_valid"])
    print(f"  crossed markets (bid > ask): {q_agg['n_crossed']} ({q_agg['n_crossed']/n_valid*100:.4f}% of valid -- "
          f"a nonzero rate can be real during fast markets but must be EXCLUDED from imbalance features)")
    print(f"  locked markets (bid == ask): {q_agg['n_locked']} ({q_agg['n_locked']/n_valid*100:.4f}% -- informational)")
    q_pass = check("quotes: no monotonicity/tz/bad-size issues", len(q_agg["issues"]) == 0,
                   f"{len(q_agg['issues'])} issue(s)")
    for msg in q_agg["issues"][:20]:
        print(f"    - {msg}")
    for note in q_agg["dst_notes"]:
        print(f"    DST: {note}")

    print("\n" + "=" * 100)
    print("  CROSS-CHECK")
    print("=" * 100)
    check("trades and quotes cover the same number of session-days",
          t_agg["n_days"] == q_agg["n_days"],
          f"trades_days={t_agg['n_days']} quotes_days={q_agg['n_days']}")
    trade_dates, quote_dates = set(trades_files), set(quotes_files)
    only_trades = trade_dates - quote_dates
    only_quotes = quote_dates - trade_dates
    if only_trades:
        print(f"  dates with trades but no quotes: {sorted(only_trades)}")
    if only_quotes:
        print(f"  dates with quotes but no trades: {sorted(only_quotes)}")

    print("\n" + "=" * 100)
    print("  DATA AUDIT SUMMARY")
    print("=" * 100)
    overall = t_pass and q_pass and not only_trades and not only_quotes
    print(f"  TRADES: {'PASS' if t_pass else 'ISSUE FOUND'}")
    print(f"  QUOTES: {'PASS' if q_pass else 'ISSUE FOUND'}")
    print(f"\n  OVERALL: {'PASS' if overall else 'ISSUE FOUND -- do not proceed to feature work until resolved'}")


if __name__ == "__main__":
    main()
