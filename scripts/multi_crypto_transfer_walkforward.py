"""
scripts/multi_crypto_transfer_walkforward.py — walk-forward version of Test A
("transfer" mode): at each BTC+ETH walk-forward fold, fit the model JOINTLY on
BTC+ETH's own TRAIN slice only (identical to scripts/walk_forward_engine.py's
fit_fold_model), derive entry-filter cutoffs (range_pos_60/realized_vol_30)
and the protective-stop/leverage from the POOLED BTC+ETH TRAIN-selected
population (matches how the original single-split Test A in
multi_crypto_screen.py --mode transfer described "BTC/ETH's own TRAIN-derived
cutoffs" as one set, not two), then apply this UNCHANGED to a third symbol's
(SOL/AVAX) TEST slice for that same calendar window -- the third symbol's own
data is NEVER used for fitting or calibration, only for out-of-sample scoring.

Why this script exists: SOL/AVAX were DEFERRED at the Etape 6 own-mode screen
(n=7 each, single-split) and their own-mode walk-forward (multi_crypto_
walkforward.py) turned out to be dominated by 1-3-trade degenerate folds with
fake PF=inf (SOL n=34/10 folds, AVAX n=16/9 folds -- not trustworthy). The
single-split Test A had a MUCH bigger population (SOL n=5465, AVAX n=6185)
because BTC+ETH's pooled TRAIN-selected population is far larger than either
new symbol's own -- this script tests whether that large population holds up
walk-forward-style (many out-of-sample folds) instead of on one static split.

Folds follow BTC/ETH's OWN calendar (standard 24mo-initial/3mo-test/3mo-step,
same as walk_forward_engine.py) since the model is fit on BTC/ETH's timeline,
not the third symbol's. SAFE_END = min(BTC HOLDOUT_START, ETH HOLDOUT_START)
= 2025-03-28, always <= SOL's own HOLDOUT_START (2025-06-13) and AVAX's
(2025-06-14) -- so this can NEVER cross either new symbol's own HOLDOUT
boundary even though it isn't explicitly re-checked per fold.

Usage:
    python scripts/multi_crypto_transfer_walkforward.py --symbol SOLUSDT --max-folds 20
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades_with_mae_mfe
from scripts.multi_crypto_walkforward import _load_full_cached, resolve_stressed, SCENARIOS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HORIZON = 10
THRESHOLD = 0.70
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0080
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INITIAL_TRAIN_MONTHS, TEST_MONTHS, STEP_MONTHS = 24, 3, 3
HOLDOUT_START = {"BTCUSDT": pd.Timestamp("2025-03-28", tz="UTC"), "ETHUSDT": pd.Timestamp("2025-04-13", tz="UTC")}
SAFE_END = min(HOLDOUT_START.values())


def build_folds(data_start, safe_end):
    folds = []
    train_end = data_start + pd.DateOffset(months=INITIAL_TRAIN_MONTHS)
    while True:
        test_end = train_end + pd.DateOffset(months=TEST_MONTHS)
        if test_end > safe_end:
            break
        folds.append((data_start, train_end, test_end))
        train_end = train_end + pd.DateOffset(months=STEP_MONTHS)
    return folds


def fit_fold_model(train_slices: dict):
    feats, labels = {}, {}
    for sym, df in train_slices.items():
        feats[sym] = build_feature_matrix(df)
        labels[sym] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X = pd.concat(feats.values(), ignore_index=True)
    y = pd.concat(labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X, y, corr_threshold=0.9)
    fit_n = min(250_000, len(X))
    fit_idx = X.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X.loc[fit_idx], y.loc[fit_idx])
    return model, feats


def process_fold(target_symbol, fold_i, btc_eth_train, target_test_df):
    model, train_feats = fit_fold_model(btc_eth_train)

    # Pooled BTC+ETH TRAIN-selected population -> ONE set of cutoffs/stop, matching
    # the single-split Test A's own description ("BTC/ETH's own TRAIN-derived cutoffs").
    pooled_feats = pd.concat(train_feats.values(), ignore_index=True)
    pooled_proba = model.predict_proba(pooled_feats)
    pooled_selected = pooled_proba > THRESHOLD
    if pooled_selected.sum() < 20:
        return None, None, None
    range_pos_cut = pooled_feats.loc[pooled_selected, "range_pos_60"].median()
    vol_cut = pooled_feats.loc[pooled_selected, "realized_vol_30"].median()

    pooled_close = np.concatenate([btc_eth_train[s]["close"].to_numpy() for s in SYMBOLS])
    pooled_filtered = (
        pooled_selected
        & (pooled_feats["range_pos_60"] < range_pos_cut)
        & (pooled_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    pooled_trades = build_trades_with_mae_mfe(
        pooled_close, pooled_filtered,
        pooled_feats["ema_slope_20"].to_numpy(), pooled_feats["ret_1"].to_numpy(),
        horizon=HORIZON)
    if len(pooled_trades) < 10:
        return None, None, None
    stop_distance = float(np.percentile(np.abs([t["mae"] for t in pooled_trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)

    # Apply UNCHANGED to the target symbol's (SOL/AVAX) TEST slice -- never fit/calibrated on it.
    target_feats = build_feature_matrix(target_test_df)
    target_proba = model.predict_proba(target_feats)
    target_filtered = (
        (target_proba > THRESHOLD)
        & (target_feats["range_pos_60"] < range_pos_cut)
        & (target_feats["realized_vol_30"] > vol_cut)
    ).to_numpy()
    target_close = target_test_df["close"].to_numpy()
    seq_trades = build_trades_with_mae_mfe(
        target_close, target_filtered,
        target_feats["ema_slope_20"].to_numpy(), target_feats["ret_1"].to_numpy(),
        horizon=HORIZON)
    if len(seq_trades) == 0:
        return {"n_trades": 0, "reason": "no TEST entries"}, [], {}

    notional = CAPITAL * RISK_PCT
    export_rows = []
    pnls, n_forced = [], 0
    for t in seq_trades:
        i = t["entry_idx"]
        path = t["close_path"]
        peak, activated, was_stopped = -np.inf, False, False
        raw_return, exit_offset = None, len(path) - 1
        for j, x in enumerate(path):
            if x <= -protective:
                raw_return, was_stopped, exit_offset = -protective, True, j
                break
            if x > peak:
                peak = x
            if not activated and peak >= ACTIVATE_AT:
                activated = True
            if activated:
                stop_level = peak - TRAIL_DIST
                if x <= stop_level:
                    raw_return, exit_offset = stop_level, j
                    break
        if raw_return is None:
            raw_return = path[-1]
        entry_time = target_test_df.index[i]
        exit_time = target_test_df.index[min(i + exit_offset, len(target_test_df) - 1)]
        export_rows.append({
            "symbol": target_symbol, "fold": fold_i, "entry_time": entry_time, "exit_time": exit_time,
            "raw_return": raw_return, "stop_distance": stop_distance, "leverage_safe": leverage,
            "was_stopped": was_stopped, "close_path": ";".join(f"{v:.8f}" for v in path),
        })
        exit_ret = raw_return - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        n_forced += int(was_stopped and liq_move <= stop_distance)
        pnls.append(exit_ret * notional * leverage)

    pnls = np.array(pnls)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    summary = {
        "n_trades": len(pnls), "profit_factor": round(pf, 3),
        "total_return_pct": round(pnls.sum() / CAPITAL * 100, 3),
        "max_dd_pct": round(float(dd.min() * 100), 3),
        "win_rate_pct": round((pnls > 0).mean() * 100, 1),
        "stop_distance_pct": round(stop_distance * 100, 3),
        "leverage": round(leverage, 2),
        "n_forced_liq": n_forced,
    }

    stress = {}
    for label, kwargs in SCENARIOS:
        spnls = []
        for t in seq_trades:
            ret = resolve_stressed(t["close_path"], protective, **kwargs)
            if ret is not None:
                spnls.append(ret * notional * leverage)
        if not spnls:
            continue
        spnls = np.array(spnls)
        swins, slosses = spnls[spnls > 0], spnls[spnls <= 0]
        spf = float(swins.sum() / -slosses.sum()) if slosses.sum() < 0 else float("inf")
        stress[label] = {"n": len(spnls), "pf": spf, "ret": spnls.sum() / CAPITAL * 100}

    return summary, export_rows, stress


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True, help="target symbol scored out-of-sample (e.g. SOLUSDT)")
    parser.add_argument("--max-folds", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=None, help="override V3's 0.70 (per-symbol optimization sweep)")
    parser.add_argument("--stop-pct", type=int, default=None, help="override V3's p90 protective-stop percentile")
    parser.add_argument("--horizon", type=int, default=None, help="override V3's 10min label horizon")
    parser.add_argument("--tag", default=None, help="output-file suffix (default: 'transfer', or 'transfer_<overrides>' for a sweep run)")
    args = parser.parse_args()
    target_symbol = args.symbol.upper()

    global THRESHOLD, STOP_PCT_PERCENTILE, HORIZON
    overrides = []
    if args.threshold is not None:
        THRESHOLD = args.threshold
        overrides.append(f"threshold{args.threshold}")
    if args.stop_pct is not None:
        STOP_PCT_PERCENTILE = args.stop_pct
        overrides.append(f"stop{args.stop_pct}")
    if args.horizon is not None:
        HORIZON = args.horizon
        # BUGFIX (2026-08-24, found during scientific-validation code audit): same bug class as
        # multi_crypto_walkforward.py's --horizon (see that file's fix comment) -- this file had NO
        # LOOKAHEAD reference at all, so build_trades_with_mae_mfe_fast would silently keep using
        # scripts.fast_trades's own default-bound HORIZON/LOOKAHEAD regardless of this override.
        # VERIFIED via reproduction that the historical SOLUSDT_transfer_horizon15/20 output files
        # were NOT affected -- their close_path lengths (56/61 points) correctly match LOOKAHEAD=
        # 15+40/20+40, meaning whatever process actually produced them patched fast_trades correctly
        # (very likely an external orchestrator script, since this file itself has never contained
        # any LOOKAHEAD-patching code) -- but the CURRENT file, run directly with --horizon, would
        # hit the bug. Fixed proactively.
        overrides.append(f"h{args.horizon}")
    tag = args.tag if args.tag is not None else ("transfer_" + "_".join(overrides) if overrides else "transfer")
    if overrides:
        print(f"[{target_symbol}] PARAMETER OVERRIDE sweep run (transfer mode): {', '.join(overrides)} (V3 defaults otherwise)")

    full = {s: _load_full_cached(s) for s in SYMBOLS}
    target_full = _load_full_cached(target_symbol)
    data_start = max(df.index[0] for df in full.values())
    folds = build_folds(data_start, SAFE_END)
    print(f"[{target_symbol}] TRANSFER-MODE walk-forward: {len(folds)} folds "
          f"(BTC+ETH-fit, scored on {target_symbol}), data_start={data_start:%Y-%m-%d} "
          f"safe_end={SAFE_END:%Y-%m-%d}")

    docs = os.path.join(os.path.dirname(__file__), "..", "docs")
    summary_path = os.path.join(docs, f"multi_crypto_wf_{target_symbol}_{tag}_summary.csv")
    export_path = os.path.join(docs, f"multi_crypto_wf_{target_symbol}_{tag}_trades.csv")
    stress_path = os.path.join(docs, f"multi_crypto_wf_{target_symbol}_{tag}_stress.csv")
    done_marker = summary_path + ".done_folds.txt"

    summary_rows, export_rows, stress_rows = [], [], []
    if os.path.exists(summary_path):
        summary_rows = pd.read_csv(summary_path).to_dict("records")
    if os.path.exists(export_path):
        export_rows = pd.read_csv(export_path).to_dict("records")
    if os.path.exists(stress_path):
        stress_rows = pd.read_csv(stress_path).to_dict("records")
    done_folds = set()
    if os.path.exists(done_marker):
        with open(done_marker) as f:
            done_folds = {int(x) for x in f.read().split() if x.strip()}
        print(f"Resuming: folds already done = {sorted(done_folds)}")

    processed = 0
    for fold_i, (t0, train_end, test_end) in enumerate(folds, 1):
        if fold_i in done_folds:
            continue
        if processed >= args.max_folds:
            print(f"Reached --max-folds={args.max_folds}, exiting cleanly.")
            break
        btc_eth_train = {s: full[s][(full[s].index >= t0) & (full[s].index < train_end)] for s in SYMBOLS}
        target_test = target_full[(target_full.index >= train_end) & (target_full.index < test_end)]
        print(f"FOLD {fold_i}/{len(folds)}: BTC+ETH TRAIN[{t0:%Y-%m-%d}->{train_end:%Y-%m-%d}] "
              f"{target_symbol} TEST[{train_end:%Y-%m-%d}->{test_end:%Y-%m-%d}] (test_n={len(target_test):,})")
        summary, erows, stress = process_fold(target_symbol, fold_i, btc_eth_train, target_test)
        if summary is None:
            print(f"  {target_symbol}: pooled BTC+ETH TRAIN population too small, skipping fold")
            summary_rows.append({"fold": fold_i, "symbol": target_symbol, "n_trades": 0, "reason": "train pop too small"})
        elif summary.get("n_trades", 0) == 0:
            print(f"  {target_symbol}: {summary.get('reason', 'no trades')}")
            summary_rows.append({"fold": fold_i, "symbol": target_symbol, **summary})
        else:
            print(f"  {target_symbol}: n={summary['n_trades']:>4} PF={summary['profit_factor']:>7.3f} "
                  f"ret={summary['total_return_pct']:>+7.3f}% DD={summary['max_dd_pct']:>+7.3f}% "
                  f"win%={summary['win_rate_pct']:>5.1f} forced_liq={summary['n_forced_liq']}")
            summary_rows.append({"fold": fold_i, "symbol": target_symbol,
                                  "train_start": t0, "train_end": train_end, "test_end": test_end, **summary})
            export_rows.extend(erows)
            srow = {"fold": fold_i, "symbol": target_symbol}
            for label, m in stress.items():
                srow[f"{label}__n"] = m["n"]
                srow[f"{label}__pf"] = m["pf"]
                srow[f"{label}__ret"] = m["ret"]
            stress_rows.append(srow)

        pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
        pd.DataFrame(export_rows).to_csv(export_path, index=False)
        pd.DataFrame(stress_rows).to_csv(stress_path, index=False)
        done_folds.add(fold_i)
        with open(done_marker, "w") as f:
            f.write(" ".join(str(x) for x in sorted(done_folds)))
        processed += 1

    remaining = [i for i in range(1, len(folds) + 1) if i not in done_folds]
    if remaining:
        print(f"\nFolds still remaining for {target_symbol}: {remaining} -- rerun to continue.")
        return

    df_res = pd.DataFrame(summary_rows)
    sub = df_res[df_res.get("n_trades", 0) > 0] if len(df_res) else df_res
    print("\n" + "=" * 100)
    print(f"  {target_symbol} TRANSFER-MODE WALK-FORWARD SUMMARY ({len(sub)}/{len(folds)} folds with trades)")
    print("=" * 100)
    if len(sub) == 0:
        print(f"{target_symbol}: no fold produced trades -- REJECT")
    else:
        pf = sub["profit_factor"].replace([np.inf], np.nan).dropna()
        print(f"  total n_trades={sub['n_trades'].sum()}  mean PF={pf.mean():.3f}  median PF={pf.median():.3f}  "
              f"%% folds PF>1: {(sub['profit_factor'] > 1).mean() * 100:.1f}%")
        print(f"  total return summed across folds: {sub['total_return_pct'].sum():+.2f}%")
        print(f"  total forced liquidations across folds: {sub['n_forced_liq'].sum()}")
    print(f"\nSaved -> {summary_path}\n         {export_path}\n         {stress_path}")


if __name__ == "__main__":
    main()
