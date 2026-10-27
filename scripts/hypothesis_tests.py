"""
scripts/hypothesis_tests.py — autonomous-session step: "pose des hypotheses
sur comment augmenter le rendement... teste-les." Tests hypotheses that
don't require the still-downloading 7yr data, reusing the frozen best
config from this session (ETH+BTC jointly-trained tier-2 model, horizon=10,
threshold=0.75, entry filter on range_pos_60/realized_vol_30, dca_rescue_trend
exit) as the baseline to beat.

H1 — Confidence-weighted position sizing: scale notional by how far proba
     is above threshold, instead of flat notional per trade. Rationale: if
     the model's probability is informative at all (AUC>0.5), higher-proba
     trades should on average have better realized returns, so sizing up on
     them and down on the marginal ones should raise risk-adjusted return
     even if it doesn't raise raw PF.
H2 — Wider rescue window: EXTENSION_CAP swept over {20, 40, 60, 80, 120}.
     Rationale: the trend-gated rescue leg only opens once ema_slope/ret_1
     confirm a resumption -- a tighter cap may be cutting off trades that
     would have recovered given a bit more time; a wider cap risks holding
     losers longer for no benefit. Sweep to find out empirically instead of
     assuming either direction.
H3 — BTC+ETH combined portfolio: run the identical filtered+dca_rescue_trend
     config on BOTH symbols' validation windows and combine into one
     portfolio equity curve (concat trades in time order per symbol, but
     report combined PF/Sharpe as if run as one book). Rationale:
     diversification across two assets whose entries don't fire on the same
     bars can reduce variance/drawdown even if neither leg's solo PF moves.

Usage:
    python scripts/hypothesis_tests.py
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

TRAIN_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
HORIZON = 10
THRESHOLD = 0.75
DEFAULT_EXTENSION_CAP = 40
COST_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST
RISK_PCT = 0.01
CAPITAL = 10_000.0


def simulate_trend_rescue(close_arr: np.ndarray, entry_mask: np.ndarray, proba_arr: np.ndarray,
                           ema_slope: np.ndarray, ret_1: np.ndarray, extension_cap: int,
                           confidence_weighted: bool = False) -> dict:
    """dca_rescue_trend exit (same logic as diagnostic_exit_strategies.py),
    parameterized by extension_cap, with an optional confidence-weighted
    notional: notional = base_notional * clip((proba-THRESHOLD)/(1-THRESHOLD), 0.25, 1.0)
    instead of a flat base_notional per trade."""
    n = len(close_arr)
    base_notional = CAPITAL * RISK_PCT
    pnls, is_rescued, sizes = [], [], []

    i = 0
    while i < n - HORIZON - extension_cap - 1:
        if not entry_mask[i]:
            i += 1
            continue

        if confidence_weighted:
            w = (proba_arr[i] - THRESHOLD) / (1.0 - THRESHOLD)
            w = min(max(w, 0.25), 1.0)  # floor at 0.25x so marginal trades aren't zeroed out
        else:
            w = 1.0
        notional = base_notional * w

        entry_price = close_arr[i]
        base_exit_price = close_arr[i + HORIZON]
        base_return = (base_exit_price / entry_price - 1.0) - COST_PCT

        if base_return >= 0:
            pnls.append(notional * base_return)
            is_rescued.append(False)
            sizes.append(w)
            i += HORIZON
            continue

        target = entry_price
        leg2_opened, entry_price2 = False, None
        exit_offset = HORIZON + extension_cap
        exit_price = close_arr[i + exit_offset]
        rescued = False
        for j in range(HORIZON, HORIZON + extension_cap + 1):
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
        sizes.append(w)
        i += exit_offset

    pnls = np.array(pnls)
    if len(pnls) == 0:
        return {"n_trades": 0}
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gl = -losses.sum()
    returns_pct_of_capital = pnls.sum() / CAPITAL * 100
    # risk-adjusted: per-trade return series (as % of CAPITAL) std-normalized
    per_trade_ret = pnls / CAPITAL
    sharpe_like = float(per_trade_ret.mean() / (per_trade_ret.std() + 1e-12))
    return {
        "n_trades": len(pnls),
        "win_rate_pct": round((pnls > 0).mean() * 100, 2),
        "profit_factor": round(float(wins.sum() / gl), 3) if gl > 0 else float("inf"),
        "total_pnl": round(float(pnls.sum()), 2),
        "total_return_pct_of_capital": round(float(returns_pct_of_capital), 3),
        "sharpe_like_per_trade": round(sharpe_like, 4),
        "avg_size_weight": round(float(np.mean(sizes)), 3),
        "n_rescued": int(sum(is_rescued)),
    }


def fit_shared_model():
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
    print(f"{len(kept)} features kept.\n")
    return model


def filtered_mask_for(symbol: str, model) -> tuple:
    """Returns (close_arr, proba_arr, filtered_mask, ema_slope_arr, ret_1_arr)
    for `symbol`'s VALIDATION split, using cutoffs computed on that symbol's
    own TRAIN-selected population (avoids leaking VALIDATION into the
    filter definition, per this session's established discipline)."""
    train_df = load_split(symbol, "train", verbose=False)
    train_feats = build_feature_matrix(train_df)
    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > THRESHOLD
    range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
    vol_cut = train_feats.loc[train_selected, "realized_vol_30"].median()

    df_val = load_split(symbol, "validation", verbose=False)
    feats_val = build_feature_matrix(df_val)
    close_val = df_val["close"]
    proba = model.predict_proba(feats_val)
    filtered_mask = (
        (proba > THRESHOLD)
        & (feats_val["range_pos_60"] < range_pos_cut)
        & (feats_val["realized_vol_30"] > vol_cut)
    ).to_numpy()
    return (close_val.to_numpy(), proba.to_numpy(), filtered_mask,
            feats_val["ema_slope_20"].to_numpy(), feats_val["ret_1"].to_numpy())


def h1_confidence_weighted_sizing(model):
    print("=" * 90)
    print("  H1 — Confidence-weighted position sizing (ETHUSDT VALIDATION)")
    print("=" * 90)
    close_arr, proba_arr, mask, ema_slope, ret_1 = filtered_mask_for("ETHUSDT", model)

    baseline = simulate_trend_rescue(close_arr, mask, proba_arr, ema_slope, ret_1,
                                      DEFAULT_EXTENSION_CAP, confidence_weighted=False)
    weighted = simulate_trend_rescue(close_arr, mask, proba_arr, ema_slope, ret_1,
                                      DEFAULT_EXTENSION_CAP, confidence_weighted=True)

    for name, m in [("flat sizing (baseline)", baseline), ("confidence-weighted", weighted)]:
        if m.get("n_trades", 0) == 0:
            print(f"  {name}: no trades")
            continue
        print(f"  {name:<26} n={m['n_trades']:>4} win%={m['win_rate_pct']:>6.1f} "
              f"PF={m['profit_factor']:>7.3f} total_ret%={m['total_return_pct_of_capital']:>8.3f} "
              f"sharpe_like={m['sharpe_like_per_trade']:>8.4f} avg_w={m['avg_size_weight']:.3f}")
    print()
    return baseline, weighted


def h2_rescue_window_sweep(model):
    print("=" * 90)
    print("  H2 — Rescue window sweep (ETHUSDT VALIDATION, extension_cap in {20,40,60,80,120})")
    print("=" * 90)
    close_arr, proba_arr, mask, ema_slope, ret_1 = filtered_mask_for("ETHUSDT", model)

    results = {}
    for cap in [20, 40, 60, 80, 120]:
        m = simulate_trend_rescue(close_arr, mask, proba_arr, ema_slope, ret_1, cap, confidence_weighted=False)
        results[cap] = m
        if m.get("n_trades", 0) == 0:
            print(f"  cap={cap:>4}min: no trades")
            continue
        print(f"  cap={cap:>4}min: n={m['n_trades']:>4} win%={m['win_rate_pct']:>6.1f} "
              f"PF={m['profit_factor']:>7.3f} total_ret%={m['total_return_pct_of_capital']:>8.3f} "
              f"n_rescued={m['n_rescued']}")
    print()
    return results


def h3_combined_portfolio(model):
    print("=" * 90)
    print("  H3 — BTC+ETH combined portfolio (both VALIDATION windows, filtered+dca_rescue_trend)")
    print("=" * 90)
    all_trade_returns = []
    per_symbol = {}
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        close_arr, proba_arr, mask, ema_slope, ret_1 = filtered_mask_for(symbol, model)
        m = simulate_trend_rescue(close_arr, mask, proba_arr, ema_slope, ret_1,
                                   DEFAULT_EXTENSION_CAP, confidence_weighted=False)
        per_symbol[symbol] = m
        if m.get("n_trades", 0) == 0:
            print(f"  {symbol}: no trades (solo)")
            continue
        print(f"  {symbol} solo: n={m['n_trades']:>4} win%={m['win_rate_pct']:>6.1f} "
              f"PF={m['profit_factor']:>7.3f} total_ret%={m['total_return_pct_of_capital']:>8.3f}")

    # Rebuild per-trade PnL series per symbol (not just the summary dict) to combine them.
    def trade_pnls(symbol, model):
        close_arr, proba_arr, mask, ema_slope, ret_1 = filtered_mask_for(symbol, model)
        n = len(close_arr)
        base_notional = CAPITAL * RISK_PCT
        pnls = []
        i = 0
        while i < n - HORIZON - DEFAULT_EXTENSION_CAP - 1:
            if not mask[i]:
                i += 1
                continue
            entry_price = close_arr[i]
            base_exit_price = close_arr[i + HORIZON]
            base_return = (base_exit_price / entry_price - 1.0) - COST_PCT
            if base_return >= 0:
                pnls.append(base_notional * base_return)
                i += HORIZON
                continue
            target = entry_price
            leg2_opened, entry_price2 = False, None
            exit_offset = HORIZON + DEFAULT_EXTENSION_CAP
            exit_price = close_arr[i + exit_offset]
            for j in range(HORIZON, HORIZON + DEFAULT_EXTENSION_CAP + 1):
                p = close_arr[i + j]
                if p >= target:
                    exit_price, exit_offset = p, j
                    break
                if not leg2_opened and ema_slope[i + j] > 0 and ret_1[i + j] > 0:
                    leg2_opened, entry_price2 = True, p
            leg1_pnl = base_notional * ((exit_price / entry_price - 1.0) - COST_PCT)
            combined = leg1_pnl
            if leg2_opened:
                combined += base_notional * ((exit_price / entry_price2 - 1.0) - COST_PCT)
            pnls.append(combined)
            i += exit_offset
        return np.array(pnls)

    btc_pnls = trade_pnls("BTCUSDT", model)
    eth_pnls = trade_pnls("ETHUSDT", model)
    combined = np.concatenate([btc_pnls, eth_pnls]) if len(btc_pnls) and len(eth_pnls) else (
        btc_pnls if len(btc_pnls) else eth_pnls)

    if len(combined) == 0:
        print("  Combined portfolio: no trades on either leg")
        return per_symbol, None

    wins, losses = combined[combined > 0], combined[combined <= 0]
    gl = -losses.sum()
    pf = float(wins.sum() / gl) if gl > 0 else float("inf")
    total_ret_pct = combined.sum() / (2 * CAPITAL) * 100  # 2x capital base: one book per symbol
    per_trade_ret = combined / (2 * CAPITAL)
    sharpe_like = float(per_trade_ret.mean() / (per_trade_ret.std() + 1e-12))
    print(f"\n  Combined portfolio (2x capital base, one allocation per symbol): "
          f"n={len(combined)}, win%={(combined>0).mean()*100:.1f}, PF={pf:.3f}, "
          f"total_ret%={total_ret_pct:+.3f}, sharpe_like={sharpe_like:.4f}")
    print("  (compare against each symbol's solo PF/return above -- diversification benefit")
    print("   shows up as combined Sharpe/PF beating the WORSE of the two solo legs, or as")
    print("   lower variance even if PF is similar.)")
    return per_symbol, {"n_trades": len(combined), "profit_factor": round(pf, 3),
                         "total_return_pct": round(total_ret_pct, 3), "sharpe_like": round(sharpe_like, 4)}


def main():
    model = fit_shared_model()
    h1_confidence_weighted_sizing(model)
    h2_rescue_window_sweep(model)
    h3_combined_portfolio(model)


if __name__ == "__main__":
    main()
