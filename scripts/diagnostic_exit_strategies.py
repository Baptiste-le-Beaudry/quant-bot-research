"""
scripts/diagnostic_exit_strategies.py — implements and compares three exit
strategies on the filtered entry signal, following up on the winner/loser
pattern analysis:

  fixed        baseline — exit at horizon (10min) no matter what
  dynamic_exit if underwater at horizon, keep holding up to extension_cap
               extra minutes, exit as soon as it crosses back to breakeven
  dca_rescue   if underwater at horizon, add a SECOND same-size position at
               the current (worse) price; close BOTH legs once price
               returns to the ORIGINAL entry (or at the extension cap if it
               never does). This is a martingale/DCA-into-losers technique:
               it can raise the apparent win rate a lot, but DOUBLES
               position size exactly on the trades that don't recover --
               reported here explicitly (max single-trade loss), not just
               averaged away.

Entry filter: proba>threshold AND range_pos_60/realized_vol_30 cutoffs
computed on the TRAIN-selected population (not on VALIDATION itself, unlike
the quick version in the last diagnostic -- avoids leaking VALIDATION into
the filter's own definition).

Usage:
    python scripts/diagnostic_exit_strategies.py
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SYMBOL = "ETHUSDT"
TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
EXTENSION_CAP = 40  # extra minutes to wait for recovery, matches the earlier
                     # "recovers within 40min" measurement
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
RISK_PCT = 0.01
CAPITAL = 10_000.0


def simulate_variant(close: pd.Series, entry_mask: np.ndarray, mode: str,
                      ema_slope: np.ndarray | None = None, ret_1: np.ndarray | None = None) -> dict:
    close_arr = close.to_numpy()
    n = len(close_arr)
    notional = CAPITAL * RISK_PCT  # fixed per-leg notional, not compounded --
                                     # keeps the three modes directly comparable
    pnls, is_rescued, max_loss = [], [], 0.0

    i = 0
    while i < n - HORIZON - EXTENSION_CAP - 1:
        if not entry_mask[i]:
            i += 1
            continue

        entry_price = close_arr[i]
        base_exit_price = close_arr[i + HORIZON]
        base_return = (base_exit_price / entry_price - 1.0) - COST_PCT

        if mode == "fixed" or base_return >= 0:
            pnl = notional * base_return
            pnls.append(pnl)
            is_rescued.append(False)
            max_loss = min(max_loss, pnl)
            i += HORIZON
            continue

        # base_return < 0 and mode wants to try to do something about it
        if mode == "dynamic_exit":
            exit_offset = HORIZON + EXTENSION_CAP
            final_return = (close_arr[i + exit_offset] / entry_price - 1.0) - COST_PCT
            rescued = False
            for j in range(HORIZON, HORIZON + EXTENSION_CAP + 1):
                r = (close_arr[i + j] / entry_price - 1.0) - COST_PCT
                if r >= 0:
                    final_return, exit_offset, rescued = r, j, True
                    break
            pnl = notional * final_return
            pnls.append(pnl)
            is_rescued.append(rescued)
            max_loss = min(max_loss, pnl)
            i += exit_offset
            continue

        if mode == "dca_rescue":
            entry_price2 = base_exit_price  # second leg opened at the worse price
            target = entry_price            # combined TP = original entry
            exit_offset, rescued = HORIZON + EXTENSION_CAP, False
            exit_price = close_arr[i + exit_offset]
            for j in range(HORIZON, HORIZON + EXTENSION_CAP + 1):
                p = close_arr[i + j]
                if p >= target:
                    exit_price, exit_offset, rescued = p, j, True
                    break
            leg1_pnl = notional * ((exit_price / entry_price - 1.0) - COST_PCT)
            leg2_pnl = notional * ((exit_price / entry_price2 - 1.0) - COST_PCT)
            combined = leg1_pnl + leg2_pnl
            pnls.append(combined)
            is_rescued.append(rescued)
            max_loss = min(max_loss, combined)
            i += exit_offset
            continue

        if mode == "dca_rescue_trend":
            # Don't open leg 2 at the worst price blindly -- wait for a trend-
            # resumption confirmation (ema_slope_20>0 AND ret_1>0), then open
            # leg 2 at THAT bar's (better) price. If leg 1 alone recovers to
            # target before any confirmation appears, just close leg 1 --
            # no need for a rescue. If neither happens by the cap, close
            # whatever's open (leg 1 alone, most of the time) at the cap price.
            target = entry_price
            leg2_opened, entry_price2 = False, None
            exit_offset = HORIZON + EXTENSION_CAP
            exit_price = close_arr[i + exit_offset]
            rescued = False
            for j in range(HORIZON, HORIZON + EXTENSION_CAP + 1):
                p = close_arr[i + j]
                if p >= target:
                    exit_price, exit_offset, rescued = p, j, leg2_opened
                    break
                if not leg2_opened and ema_slope[i + j] > 0 and ret_1[i + j] > 0:
                    leg2_opened = True
                    entry_price2 = p
            leg1_pnl = notional * ((exit_price / entry_price - 1.0) - COST_PCT)
            if leg2_opened:
                leg2_pnl = notional * ((exit_price / entry_price2 - 1.0) - COST_PCT)
                combined = leg1_pnl + leg2_pnl
            else:
                combined = leg1_pnl
            pnls.append(combined)
            is_rescued.append(rescued)
            max_loss = min(max_loss, combined)
            i += exit_offset
            continue

    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gl = -losses.sum()
    return {
        "n_trades": len(pnls),
        "win_rate_pct": round((pnls > 0).mean() * 100, 2),
        "profit_factor": round(float(wins.sum() / gl), 3) if gl > 0 else float("inf"),
        "total_pnl": round(float(pnls.sum()), 2),
        "total_return_pct_of_capital": round(float(pnls.sum() / CAPITAL * 100), 3),
        "max_single_trade_loss": round(float(max_loss), 2),
        "max_single_trade_loss_pct_notional": round(float(max_loss / notional * 100), 2),
        "n_rescued": int(sum(is_rescued)),
        "pct_rescued_of_would_be_losses": round(sum(is_rescued) / max((pnls <= 0).sum() + sum(is_rescued), 1) * 100, 1),
    }


def main():
    print("Fitting tier-2 classifier, horizon=10min...")
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

    # Entry filter cutoffs computed on TRAIN's own model-selected population
    # (proba>threshold there), NOT on VALIDATION -- avoids the leak in the
    # quick version from the earlier diagnostic.
    train_df_eth = load_split("ETHUSDT", "train", verbose=False)
    train_feats_eth = build_feature_matrix(train_df_eth)
    train_proba = model.predict_proba(train_feats_eth)
    train_selected = train_proba > THRESHOLD
    range_pos_cut = train_feats_eth.loc[train_selected, "range_pos_60"].median()
    vol_cut = train_feats_eth.loc[train_selected, "realized_vol_30"].median()
    print(f"Filter cutoffs (from TRAIN): range_pos_60 < {range_pos_cut:.4f}, "
          f"realized_vol_30 > {vol_cut:.6f}\n")

    df_val = load_split(SYMBOL, "validation", verbose=False)
    feats_val = build_feature_matrix(df_val)
    close_val = df_val["close"]
    proba = model.predict_proba(feats_val)

    baseline_mask = (proba > THRESHOLD).to_numpy()
    filtered_mask = (
        (proba > THRESHOLD)
        & (feats_val["range_pos_60"] < range_pos_cut)
        & (feats_val["realized_vol_30"] > vol_cut)
    ).to_numpy()
    print(f"Baseline entries: {baseline_mask.sum()} | Filtered entries: {filtered_mask.sum()}\n")

    ema_slope_arr = feats_val["ema_slope_20"].to_numpy()
    ret_1_arr = feats_val["ret_1"].to_numpy()

    print("=" * 100)
    print(f"{'entry':<12}{'exit mode':<18}{'n':>6}{'win%':>7}{'PF':>8}{'total_ret%':>11}"
          f"{'worst_trade%':>13}{'n_rescued':>11}{'%_of_losers_rescued':>21}")
    print("-" * 100)
    for entry_name, mask in [("baseline", baseline_mask), ("filtered", filtered_mask)]:
        for mode in ["fixed", "dynamic_exit", "dca_rescue", "dca_rescue_trend"]:
            m = simulate_variant(close_val, mask, mode, ema_slope=ema_slope_arr, ret_1=ret_1_arr)
            if m.get("n_trades", 0) == 0:
                print(f"{entry_name:<12}{mode:<18}{'no trades'}")
                continue
            print(f"{entry_name:<12}{mode:<18}{m['n_trades']:>6}{m['win_rate_pct']:>7.1f}"
                  f"{m['profit_factor']:>8.3f}{m['total_return_pct_of_capital']:>11.3f}"
                  f"{m['max_single_trade_loss_pct_notional']:>13.2f}{m['n_rescued']:>11}"
                  f"{m['pct_rescued_of_would_be_losses']:>20.1f}%")

    print("\nworst_trade%: single worst trade's P&L as % of ONE LEG's notional (not equity) --")
    print("  for dca_rescue this can exceed -100% since it's 2 legs' combined loss vs a 1-leg")
    print("  notional reference, on purpose: shows the real cost of the 2nd leg when it doesn't")
    print("  recover, not hidden by dividing over a bigger notional base.")


if __name__ == "__main__":
    main()
