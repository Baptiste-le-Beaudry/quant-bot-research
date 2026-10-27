"""
scripts/trailing_stop_oos_test.py — anti-overfitting check on the trailing-
stop exit discovered in scripts/mae_mfe_analysis.py (ETHUSDT VALIDATION,
n=89: activate at +0.63% MFE, trail 0.20-0.40% behind peak -> avg_ret
+0.24%/trade, PF~1.55, vs the current dca_rescue_trend exit's +0.10%/trade).

That discovery swept several trail distances on the SAME 89 ETH trades it
was found on -- a real risk of picking the grid point that happened to fit
this particular window best, not a genuinely better exit rule. The test
here: FREEZE the rule exactly as found on ETH (activate_at=0.63%,
trail_dist=0.30% -- the midpoint of the 0.20/0.40% near-tie, chosen instead
of the single best grid point specifically to avoid picking an overfit
optimum) and apply it UNCHANGED to BTCUSDT VALIDATION -- no recalibration,
no re-sweep, no re-picking activate_at from BTC's own MFE distribution.
If it still beats BTC's own dca_rescue_trend baseline by a comparable
margin, the exit rule is far more likely to be real than a validation-set
artifact. Also re-runs on ETH for a side-by-side sanity check (should
closely reproduce the original sweep's 0.20/0.40% rows).

Usage:
    python scripts/trailing_stop_oos_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.phase3_baseline import load_split
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe, apply_trailing_stop

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST

# FROZEN rule, discovered on ETHUSDT VALIDATION only -- NOT re-derived per symbol below.
ACTIVATE_AT = 0.0063
TRAIL_DIST = 0.0030


def get_trades_for(symbol: str, model) -> list[dict]:
    train_df_sym = load_split(symbol, "train", verbose=False)
    train_feats_sym = build_feature_matrix(train_df_sym)
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
    vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

    df_val = load_split(symbol, "validation", verbose=False)
    feats_val = build_feature_matrix(df_val)
    close_val = df_val["close"]
    proba = model.predict_proba(feats_val)
    filtered_mask = (
        (proba > THRESHOLD)
        & (feats_val["range_pos_60"] < range_pos_cut)
        & (feats_val["realized_vol_30"] > vol_cut)
    ).to_numpy()

    close_arr = close_val.to_numpy()
    ema_slope_arr = feats_val["ema_slope_20"].to_numpy()
    ret_1_arr = feats_val["ret_1"].to_numpy()
    return build_trades_with_mae_mfe(close_arr, filtered_mask, ema_slope_arr, ret_1_arr)


def report(symbol: str, trades: list[dict]) -> None:
    baseline = np.array([t["pnl_return"] for t in trades])
    trailing = apply_trailing_stop(trades, ACTIVATE_AT, TRAIL_DIST)

    def stats(rets):
        wins, losses = rets[rets > 0], rets[rets <= 0]
        pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
        return rets.mean() * 100, pf, (rets > 0).mean() * 100

    b_avg, b_pf, b_win = stats(baseline)
    t_avg, t_pf, t_win = stats(trailing)
    n_changed = int((trailing != baseline).sum())

    print(f"\n{symbol} VALIDATION (n={len(trades)}):")
    print(f"  {'exit':<28}{'avg_ret/trade':>16}{'PF':>10}{'win%':>10}")
    print(f"  {'dca_rescue_trend (baseline)':<28}{b_avg:>+15.4f}%{b_pf:>10.3f}{b_win:>9.1f}%")
    print(f"  {'frozen trailing (from ETH)':<28}{t_avg:>+15.4f}%{t_pf:>10.3f}{t_win:>9.1f}%"
          f"   ({n_changed}/{len(trades)} trades exited early via trailing)")
    verdict = "BEATS baseline" if t_avg > b_avg and t_pf > b_pf else (
        "MIXED (one metric up, one down)" if (t_avg > b_avg) != (t_pf > b_pf) else "WORSE than baseline")
    print(f"  -> {verdict}")


def main():
    print("Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min...")
    train_feats, train_labels = {}, {}
    for symbol in TRAIN_SYMBOLS:
        df = load_split(symbol, "train", verbose=False)
        train_feats[symbol] = build_feature_matrix(df)
        train_labels[symbol] = build_labels(df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    X_train = pd.concat(train_feats.values(), ignore_index=True)
    y_train = pd.concat(train_labels.values(), ignore_index=True)
    kept, _ = prune_redundant(X_train, y_train, corr_threshold=0.9)
    fit_n = min(250_000, len(X_train))
    fit_idx = X_train.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(X_train.loc[fit_idx], y_train.loc[fit_idx])
    print(f"{len(kept)} features kept.")

    print(f"\nFROZEN rule (derived on ETHUSDT only, NOT re-tuned per symbol): "
          f"activate at +{ACTIVATE_AT*100:.2f}%, trail {TRAIL_DIST*100:.2f}% behind peak.")
    print("=" * 90)
    print("  Sanity check (ETH) + out-of-sample test (BTC) of the SAME frozen rule")
    print("=" * 90)

    for symbol in ["ETHUSDT", "BTCUSDT"]:
        trades = get_trades_for(symbol, model)
        report(symbol, trades)


if __name__ == "__main__":
    main()
