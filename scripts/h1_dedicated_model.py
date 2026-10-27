"""
scripts/h1_dedicated_model.py — H1 version of the bot using the full
best-known pipeline discovered on 1-min (scripts/btc_dedicated_model.py,
scripts/hypothesis_tests.py): a dedicated per-symbol model + entry filter
(range_pos/realized_vol, cutoffs computed on TRAIN's own threshold-selected
population, never on VALIDATION) + trend-gated rescue exit (dca_rescue_trend)
— instead of scripts/h1_multi_asset_test.py's naive fixed-horizon-only
pipeline (quant_bot.backtest.engine.simulate: raw threshold, no filter, no
rescue leg), which is what produced the weak H1 result reported in
docs/autonomous_session_plan.md (AUC 0.52-0.59, negligible/negative return,
badly underperforming buy-and-hold on every symbol). That pipeline was never
actually the one that worked on 1-min — the 1-min "best result" (PF=1.463)
came from the entry filter + rescue exit combo, which H1 never got tested
with. This script applies the same components, on top of the H1-adapted
feature windows already built into quant_bot.features.build_h1, to check
whether the earlier weak H1 result was a pipeline gap rather than an
intrinsic property of the H1 timeframe.

extension_cap is swept as a multiple of horizon rather than assumed: the
1-min config's cap=40 at horizon=10 (4x) was itself the result of an
empirical sweep (H2 in hypothesis_tests.py), not a first guess, so there's
no reason to assume 4x transfers unchanged to hourly bars.

Usage:
    python scripts/h1_dedicated_model.py [--symbol BTCUSDT|ETHUSDT|NQUSD]
    (default: runs all three)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from quant_bot.config import ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build_h1 import build_feature_matrix_h1, build_labels_h1
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from quant_bot.backtest.engine import buy_and_hold
from quant_bot.data.h1_loader import load_h1_split

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOLS = ["BTCUSDT", "ETHUSDT", "NQUSD"]
HORIZONS = [4, 8, 24]  # hours
THRESHOLDS = [0.55, 0.60, 0.65, 0.70, 0.75]
CAP_MULTIPLIERS = [2, 4, 8]  # extension_cap = multiplier * horizon
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
RISK_PCT = 0.01
CAPITAL = 10_000.0


def simulate_trend_rescue_h1(close_arr: np.ndarray, entry_mask: np.ndarray,
                              ema_slope: np.ndarray, ret_1: np.ndarray,
                              horizon: int, extension_cap: int) -> dict:
    """H1 analogue of scripts/hypothesis_tests.py:simulate_trend_rescue,
    generalized over horizon (H1 sweeps horizon per symbol instead of using
    one fixed value like the 1-min config's HORIZON=10)."""
    n = len(close_arr)
    notional = CAPITAL * RISK_PCT
    pnls, is_rescued = [], []

    i = 0
    while i < n - horizon - extension_cap - 1:
        if not entry_mask[i]:
            i += 1
            continue

        entry_price = close_arr[i]
        base_exit_price = close_arr[i + horizon]
        base_return = (base_exit_price / entry_price - 1.0) - COST_PCT

        if base_return >= 0:
            pnls.append(notional * base_return)
            is_rescued.append(False)
            i += horizon
            continue

        target = entry_price
        leg2_opened, entry_price2 = False, None
        exit_offset = horizon + extension_cap
        exit_price = close_arr[i + exit_offset]
        rescued = False
        for j in range(horizon, horizon + extension_cap + 1):
            p = close_arr[i + j]
            if p >= target:
                exit_price, exit_offset, rescued = p, j, leg2_opened
                break
            if not leg2_opened and ema_slope[i + j] > 0 and ret_1[i + j] > 0:
                leg2_opened, entry_price2 = True, p
        leg1_pnl = notional * ((exit_price / entry_price - 1.0) - COST_PCT)
        if leg2_opened:
            leg2_pnl = notional * ((exit_price / entry_price2 - 1.0) - COST_PCT)
            combined = leg1_pnl + leg2_pnl
        else:
            combined = leg1_pnl
        pnls.append(combined)
        is_rescued.append(rescued)
        i += exit_offset

    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gl = -losses.sum()
    return {
        "n_trades": len(pnls),
        "win_rate_pct": round((pnls > 0).mean() * 100, 2),
        "profit_factor": round(float(wins.sum() / gl), 3) if gl > 0 else float("inf"),
        "total_return_pct": round(float(pnls.sum() / CAPITAL * 100), 3),
        "n_rescued": int(sum(is_rescued)),
    }


def run_symbol(symbol: str) -> list[dict]:
    print("\n" + "=" * 90)
    print(f"  {symbol} H1 — dedicated model + entry filter + trend-gated rescue exit")
    print("=" * 90)

    train_df = load_h1_split(symbol, "train")
    train_feats = build_feature_matrix_h1(train_df)
    val_df = load_h1_split(symbol, "validation")
    val_feats = build_feature_matrix_h1(val_df)
    val_close = val_df["close"]
    bh = buy_and_hold(val_close)
    print(f"Buy & hold over VALIDATION: {bh['total_return_pct']:+.2f}%")

    results = []
    for h in HORIZONS:
        y_train = build_labels_h1(train_df["close"], h, COST_PCT, direction="long")
        kept, _ = prune_redundant(train_feats, y_train, corr_threshold=0.9)
        model = Tier2RandomForestSignal(kept, n_estimators=100).fit(train_feats, y_train)

        y_val = build_labels_h1(val_close, h, COST_PCT, direction="long")
        proba_val = model.predict_proba(val_feats)
        proba_train = model.predict_proba(train_feats)
        valid_val = proba_val.notna() & y_val.notna()
        if valid_val.sum() < 20 or y_val[valid_val].nunique() < 2:
            print(f"\n  --- horizon={h}h --- not enough valid/varied VALIDATION data, skipping")
            continue
        auc = roc_auc_score(y_val[valid_val], proba_val[valid_val])
        print(f"\n  --- horizon={h}h --- AUC={auc:.4f}")

        close_arr = val_close.to_numpy()
        ema_slope_arr = val_feats["ema_slope_20"].to_numpy()
        ret_1_arr = val_feats["ret_1"].to_numpy()
        proba_arr = proba_val.to_numpy()

        for thresh in THRESHOLDS:
            train_selected = proba_train > thresh
            if train_selected.sum() < 20:
                print(f"    threshold={thresh}: train-selected population < 20, skipping")
                continue

            unfiltered_mask = (proba_val > thresh).to_numpy()
            range_pos_cut = train_feats.loc[train_selected, "range_pos_24"].median()
            vol_cut = train_feats.loc[train_selected, "realized_vol_24"].median()
            filtered_mask = (
                (proba_val > thresh)
                & (val_feats["range_pos_24"] < range_pos_cut)
                & (val_feats["realized_vol_24"] > vol_cut)
            ).to_numpy()

            for variant, mask in [("no-filter", unfiltered_mask), ("filtered", filtered_mask)]:
                n_sel = int(mask.sum())
                if n_sel < 5:
                    print(f"    threshold={thresh} [{variant}]: only {n_sel} entries, skipping")
                    continue
                for mult in CAP_MULTIPLIERS:
                    cap = mult * h
                    m = simulate_trend_rescue_h1(close_arr, mask, ema_slope_arr, ret_1_arr, h, cap)
                    if m.get("n_trades", 0) == 0:
                        print(f"    threshold={thresh} [{variant}], cap={cap}h ({mult}x): no trades")
                        continue
                    reliable = "n>100" if m["n_trades"] > 100 else "n<100 !!"
                    print(f"    threshold={thresh} [{variant:>9}], cap={cap:>3}h ({mult}x): n_sel={n_sel}, "
                          f"n_trades={m['n_trades']}, win%={m['win_rate_pct']:.1f}, "
                          f"PF={m['profit_factor']:.3f}, total_ret={m['total_return_pct']:+.3f}%, "
                          f"rescued={m['n_rescued']} [{reliable}]")
                    results.append({"symbol": symbol, "horizon_h": h, "threshold": thresh,
                                     "variant": variant, "cap_mult": mult, "extension_cap_h": cap,
                                     "auc": auc, "n_filtered": n_sel, **m})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=SYMBOLS, default=None)
    args = parser.parse_args()
    symbols = [args.symbol] if args.symbol else SYMBOLS

    all_results = []
    for symbol in symbols:
        all_results.extend(run_symbol(symbol))

    print("\n\n" + "=" * 90)
    print("  SUMMARY — best (n>100) result per symbol by profit factor")
    print("=" * 90)
    df_res = pd.DataFrame(all_results)
    if len(df_res):
        reliable = df_res[df_res["n_trades"] > 100]
        for symbol in symbols:
            for variant in ["no-filter", "filtered"]:
                sub = reliable[(reliable["symbol"] == symbol) & (reliable["variant"] == variant)]
                if len(sub) == 0:
                    print(f"{symbol} [{variant}]: no reliable (n>100) result found")
                    continue
                best = sub.loc[sub["profit_factor"].idxmax()]
                print(f"{symbol} [{variant}]: horizon={best['horizon_h']}h, threshold={best['threshold']}, "
                      f"cap={best['extension_cap_h']}h, n={best['n_trades']}, "
                      f"PF={best['profit_factor']:.3f}, total_ret={best['total_return_pct']:+.3f}%")
    else:
        print("No results produced.")
    print("\nCaveat: NQUSD uses crypto fee/slippage assumptions as a first pass, not a")
    print("precise equity-futures cost model (carried over from h1_multi_asset_test.py).")


if __name__ == "__main__":
    main()
