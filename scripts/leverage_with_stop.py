"""
scripts/leverage_with_stop.py — fixes the failure mode found in
scripts/diagnostic_leverage.py: at 15x leverage with NO voluntary stop-loss,
positions rode until either their normal exit OR the exchange's forced
margin liquidation (0.5/leverage adverse move, diagnostic_leverage.py's
conservative 50%-margin-loss rule) — and that liquidation threshold turned
out to be TIGHTER than the routine drawdown the dca_rescue_trend exit's own
logic needs to absorb before recovering, so leverage was converting
would-have-recovered trades into forced losses (PF 1.463 -> 0.886,
docs/autonomous_session_plan.md hypothesis list, item 1).

The fix tested here: size leverage FROM the strategy's own historical max
adverse excursion (MAE) distribution, and add a real VOLUNTARY stop-loss
placed just outside routine noise (a chosen percentile of leg1 MAE across
ALL historical trades, winners and losers alike, with a safety buffer) but
safely inside the exchange's liquidation threshold. A stop that fires before
liquidation is a controlled, known loss (no liquidation fees/slippage/funding
pile-on); one that fires only outside the percentile band should rarely clip
a trade that would otherwise have recovered.

Usage:
    python scripts/leverage_with_stop.py [--symbol BTCUSDT|ETHUSDT]
"""
import argparse
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
from scripts.diagnostic_leverage import build_trades_with_mae, STOP_OUT_FRACTION

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
EXTENSION_CAP = 40
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
RISK_PCT = 0.01
CAPITAL = 10_000.0
STOP_PERCENTILES = [80, 90, 95]
SAFETY_MARGIN = 0.75  # only use 75% of the leverage the stop distance would technically allow,
                       # leaving room for stop-fill slippage/gap risk (the stop is simulated as
                       # an exact-price fill here, which is optimistic -- this buffer partly
                       # compensates without needing a full slippage model)


def simulate_leveraged_with_stop(close_arr: np.ndarray, entry_mask: np.ndarray,
                                  ema_slope: np.ndarray, ret_1: np.ndarray,
                                  leverage: float, stop_distance: float) -> list[dict]:
    """Same bar-by-bar dca_rescue_trend replay as
    diagnostic_leverage.simulate_leveraged_trades, but each leg now has TWO
    adverse thresholds: the voluntary stop (stop_distance, checked first --
    it's the tighter one by construction) and the exchange's forced
    liquidation (0.5/leverage, kept as a backstop in case stop_distance was
    set too loose for the chosen leverage -- should essentially never fire
    if the leverage/stop pairing is sane, but this is what would actually
    happen if it did)."""
    liq_move = STOP_OUT_FRACTION / leverage
    n = len(close_arr)
    trades = []
    i = 0
    while i < n - HORIZON - EXTENSION_CAP - 1:
        if not entry_mask[i]:
            i += 1
            continue

        entry_price = close_arr[i]
        leg1_stopped, leg1_exit_return, leg1_liq = False, None, False
        leg2_opened, entry_price2 = False, None
        leg2_stopped, leg2_exit_return, leg2_liq = False, False, None
        target = entry_price
        final_j = HORIZON + EXTENSION_CAP

        for j in range(0, HORIZON + EXTENSION_CAP + 1):
            p = close_arr[i + j]

            if not leg1_stopped:
                move = p / entry_price - 1.0
                if move <= -liq_move:
                    leg1_stopped, leg1_exit_return, leg1_liq = True, -liq_move - COST_PCT, True
                elif move <= -stop_distance:
                    leg1_stopped, leg1_exit_return, leg1_liq = True, -stop_distance - COST_PCT, False

            if leg2_opened and not leg2_stopped:
                move2 = p / entry_price2 - 1.0
                if move2 <= -liq_move:
                    leg2_stopped, leg2_exit_return, leg2_liq = True, -liq_move - COST_PCT, True
                elif move2 <= -stop_distance:
                    leg2_stopped, leg2_exit_return, leg2_liq = True, -stop_distance - COST_PCT, False

            if j >= HORIZON:
                if not leg1_stopped and leg1_exit_return is None and p >= target:
                    leg1_exit_return = (p / entry_price - 1.0) - COST_PCT
                if leg2_opened and not leg2_stopped and leg2_exit_return is None and p >= target:
                    leg2_exit_return = (p / entry_price2 - 1.0) - COST_PCT
                if (not leg2_opened and not leg1_stopped and leg1_exit_return is None
                        and ema_slope[i + j] > 0 and ret_1[i + j] > 0):
                    leg2_opened, entry_price2 = True, p

            if (leg1_stopped or leg1_exit_return is not None) and (
                    not leg2_opened or leg2_stopped or leg2_exit_return is not None):
                final_j = j
                break
        else:
            p = close_arr[i + final_j]
            if leg1_exit_return is None and not leg1_stopped:
                leg1_exit_return = (p / entry_price - 1.0) - COST_PCT
            if leg2_opened and leg2_exit_return is None and not leg2_stopped:
                leg2_exit_return = (p / entry_price2 - 1.0) - COST_PCT

        r1 = leg1_exit_return if leg1_exit_return is not None else -stop_distance - COST_PCT
        combined = r1 + (leg2_exit_return if (leg2_opened and leg2_exit_return is not None) else 0.0)
        trades.append({
            "pnl_return": combined,
            "leg1_stopped": leg1_stopped, "leg1_liquidated": leg1_liq,
            "leg2_stopped": leg2_opened and leg2_stopped, "leg2_liquidated": leg2_opened and leg2_liq,
            "rescued": leg2_opened,
        })
        i += final_j if final_j > 0 else HORIZON

    return trades


def report(trades: list[dict], leverage: float, stop_distance: float, label: str) -> dict:
    notional_1x = CAPITAL * RISK_PCT
    returns = np.array([t["pnl_return"] for t in trades])
    pnl_dollars = returns * notional_1x * leverage
    total_pnl = pnl_dollars.sum()
    wins, losses = pnl_dollars[pnl_dollars > 0], pnl_dollars[pnl_dollars <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    n_stopped = sum(t.get("leg1_stopped", False) for t in trades)
    n_liquidated = sum(t.get("leg1_liquidated", False) for t in trades)
    n_rescued = sum(t["rescued"] for t in trades)

    eq = CAPITAL + np.cumsum(pnl_dollars)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    max_dd_pct = float(dd.min() * 100)

    print(f"{label:<40} lev={leverage:>5.1f}x stop={stop_distance*100:>5.2f}%  n={len(trades):>4} "
          f"win%={((pnl_dollars>0).mean()*100):>5.1f} PF={pf:>7.3f} "
          f"total_ret={total_pnl/CAPITAL*100:>+7.2f}% max_DD={max_dd_pct:>+7.2f}% "
          f"stopped={n_stopped}({n_liquidated} forced) rescued={n_rescued}")
    return {"leverage": leverage, "stop_distance": stop_distance, "n_trades": len(trades),
            "profit_factor": round(pf, 3), "total_return_pct": round(total_pnl / CAPITAL * 100, 3),
            "max_dd_pct": round(max_dd_pct, 3), "n_stopped": n_stopped, "n_liquidated": n_liquidated}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], default="ETHUSDT")
    args = parser.parse_args()
    SYMBOL = args.symbol

    print(f"Fitting tier-2 classifier (BTC+ETH jointly), horizon=10min, evaluating on {SYMBOL}...")
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
    print(f"{len(kept)} features kept.\n")

    train_df_sym = load_split(SYMBOL, "train", verbose=False)
    train_feats_sym = build_feature_matrix(train_df_sym)
    train_proba_sym = model.predict_proba(train_feats_sym)
    train_selected_sym = train_proba_sym > THRESHOLD
    range_pos_cut = train_feats_sym.loc[train_selected_sym, "range_pos_60"].median()
    vol_cut = train_feats_sym.loc[train_selected_sym, "realized_vol_30"].median()

    df_val = load_split(SYMBOL, "validation", verbose=False)
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

    # Step 1: historical MAE distribution (no leverage, no stop) to calibrate stop distances from.
    trades_no_lev = build_trades_with_mae(close_arr, filtered_mask, ema_slope_arr, ret_1_arr)
    leg1_maes = np.array([abs(t["leg1_mae"]) for t in trades_no_lev])
    print("=" * 100)
    print(f"  STEP 1 — leg1 MAE distribution across all {len(leg1_maes)} historical trades (no leverage/stop)")
    print("=" * 100)
    for pct in [50, 80, 90, 95, 99, 100]:
        print(f"  p{pct}: {np.percentile(leg1_maes, pct)*100:.3f}%")

    print("\n" + "=" * 100)
    print("  STEP 2 — 1x baseline (no leverage, no stop) for comparison")
    print("=" * 100)
    report(trades_no_lev, leverage=1.0, stop_distance=1.0, label="1x, no stop")

    print("\n" + "=" * 100)
    print("  STEP 3 — for each stop percentile, the self-consistent leverage ceiling and result")
    print("=" * 100)
    print("  (leverage ceiling = SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, so the")
    print("   exchange's own liquidation sits comfortably beyond the voluntary stop)\n")
    results = []
    for pct in STOP_PERCENTILES:
        stop_distance = float(np.percentile(leg1_maes, pct))
        max_leverage = SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance
        for lev in sorted(set([round(max_leverage, 1), round(max_leverage * 0.5, 1), round(max_leverage * 2, 1)])):
            if lev < 1:
                continue
            trades = simulate_leveraged_with_stop(close_arr, filtered_mask, ema_slope_arr, ret_1_arr,
                                                    leverage=lev, stop_distance=stop_distance)
            r = report(trades, lev, stop_distance, label=f"p{pct} stop")
            results.append(r)

    print("\n" + "=" * 100)
    print("  STEP 4 — reference point: naive 15x with NO voluntary stop (diagnostic_leverage.py result)")
    print("=" * 100)
    print("  PF=0.886, total_ret=-0.29% (3/36 trades force-liquidated) -- compare against the")
    print("  p80/p90-calibrated results above at similar or higher leverage.")


if __name__ == "__main__":
    main()
