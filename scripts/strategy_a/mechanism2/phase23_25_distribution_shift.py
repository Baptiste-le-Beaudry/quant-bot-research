"""Phases 23-25: feature-distribution shift (PSI/KS/Wasserstein) between
crypto's Strategy-A-relevant feature space and QQQ/SPY; model-
extrapolation check (TYPE A "no setups" vs TYPE B "same setup, different
outcome"); a descriptive nearest-neighbor matched-event test. Reuses the
already-built QQQ/SPY 1-min bars from the prior cross-market report
(docs/strategy_a/mechanism/QQQ_1min_bars.parquet, SPY_1min_bars.parquet)
-- no tick-data rebuild.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
from scipy import stats

from common import MECH2_DOCS, REPO_ROOT, load_symbol
from quant_bot.features.build import build_feature_matrix

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MECH1_DOCS = os.path.join(REPO_ROOT, "docs", "strategy_a", "mechanism")
CANDIDATE_FEATURES = ["vwap_dist_z_60", "vwap_dist_z_240", "autocorr_60", "autocorr_240", "hurst_120",
                       "ret_1", "ret_5", "ret_15", "ret_60", "dist_ema20_atr", "dist_ema50_atr",
                       "dist_ema200_atr", "ema_slope_20", "dist_high_60_atr", "dist_low_60_atr",
                       "range_pos_60", "atr_norm", "realized_vol_30", "realized_vol_ratio",
                       "range_expansion", "rel_volume_20", "volume_accel", "taker_imbalance_20",
                       "volume_to_vol_ratio"]


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    quantiles = np.linspace(0, 1, bins + 1)
    cuts = np.unique(np.quantile(expected, quantiles))
    if len(cuts) < 3:
        return np.nan
    e_counts, _ = np.histogram(expected, bins=cuts)
    a_counts, _ = np.histogram(actual, bins=cuts)
    e_pct = np.clip(e_counts / max(1, e_counts.sum()), 1e-6, None)
    a_pct = np.clip(a_counts / max(1, a_counts.sum()), 1e-6, None)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


def main():
    qqq = pd.read_parquet(os.path.join(MECH1_DOCS, "QQQ_1min_bars.parquet"))
    spy = pd.read_parquet(os.path.join(MECH1_DOCS, "SPY_1min_bars.parquet"))
    # Equity trade data has no taker buy/sell split (a crypto-perp-specific field) -- supply NaN
    # columns so build_feature_matrix's taker_imbalance_20 correctly comes out NaN (missing data),
    # not fabricated, while every other feature computes normally.
    for df in (qqq, spy):
        if "taker_buy_volume" not in df.columns:
            df["taker_buy_volume"] = np.nan
            df["taker_sell_volume"] = np.nan
    qqq_feats = build_feature_matrix(qqq)
    spy_feats = build_feature_matrix(spy)

    btc = load_symbol("BTCUSDT")
    eth = load_symbol("ETHUSDT")
    btc_feats = build_feature_matrix(btc)
    eth_feats = build_feature_matrix(eth)

    trades = pd.read_csv(os.path.join(REPO_ROOT, "docs", "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv"),
                          parse_dates=["entry_time"])
    btc_h_times = trades.loc[trades["symbol"] == "BTCUSDT", "entry_time"]
    eth_h_times = trades.loc[trades["symbol"] == "ETHUSDT", "entry_time"]
    btc_h_feats = btc_feats.reindex(btc_h_times).dropna(how="all")
    eth_h_feats = eth_feats.reindex(eth_h_times).dropna(how="all")

    rows = []
    for feat in CANDIDATE_FEATURES:
        if feat not in qqq_feats.columns or feat not in btc_feats.columns:
            continue
        crypto_generic = pd.concat([btc_feats[feat], eth_feats[feat]]).dropna()
        crypto_selected = pd.concat([btc_h_feats.get(feat, pd.Series(dtype=float)),
                                      eth_h_feats.get(feat, pd.Series(dtype=float))]).dropna()
        for idx_name, idx_feats in [("QQQ", qqq_feats), ("SPY", spy_feats)]:
            idx_vals = idx_feats[feat].dropna()
            if len(idx_vals) < 30 or len(crypto_generic) < 30:
                continue
            ks = stats.ks_2samp(crypto_generic, idx_vals)
            wass = stats.wasserstein_distance(crypto_generic, idx_vals)
            psi_val = psi(crypto_generic.to_numpy(), idx_vals.to_numpy())
            row = {"feature": feat, "index": idx_name, "n_crypto_generic": len(crypto_generic),
                   "n_index": len(idx_vals), "crypto_generic_median": float(crypto_generic.median()),
                   "index_median": float(idx_vals.median()), "ks_stat": float(ks.statistic),
                   "ks_pvalue": float(ks.pvalue), "wasserstein": float(wass), "psi": psi_val}
            if len(crypto_selected) >= 10:
                row["crypto_selected_median"] = float(crypto_selected.median())
                row["ks_stat_vs_selected"] = float(stats.ks_2samp(crypto_selected, idx_vals).statistic)
            rows.append(row)
    dist_df = pd.DataFrame(rows)
    dist_path = os.path.join(MECH2_DOCS, "strategy_a_feature_distribution_shift.csv")
    dist_df.to_csv(dist_path, index=False)
    print(f"Saved -> {dist_path} ({len(dist_df)} rows)")

    # ---- Phase 24: model extrapolation check (TYPE A vs TYPE B) ----
    # For each of QQQ/SPY, what fraction of bars fall within the crypto Strategy-A-selected
    # population's own [p5, p95] envelope for range_pos_60 and realized_vol_30 jointly?
    extrap_rows = []
    for idx_name, idx_feats in [("QQQ", qqq_feats), ("SPY", spy_feats)]:
        for feat in ["range_pos_60", "realized_vol_30"]:
            sel = pd.concat([btc_h_feats.get(feat, pd.Series(dtype=float)),
                             eth_h_feats.get(feat, pd.Series(dtype=float))]).dropna()
            if len(sel) < 10:
                continue
            lo, hi = sel.quantile(0.05), sel.quantile(0.95)
            idx_vals = idx_feats[feat].dropna()
            in_range = idx_vals.between(lo, hi)
            extrap_rows.append({"index": idx_name, "feature": feat, "selected_p5": float(lo), "selected_p95": float(hi),
                                 "pct_index_bars_in_selected_envelope": float(in_range.mean()) * 100, "n_index_bars": len(idx_vals)})
    extrap_df = pd.DataFrame(extrap_rows)
    extrap_path = os.path.join(MECH2_DOCS, "strategy_a_model_extrapolation_check.csv")
    extrap_df.to_csv(extrap_path, index=False)
    print(f"Saved -> {extrap_path} ({len(extrap_df)} rows)")

    # ---- Phase 25: descriptive matched-event nearest-neighbor test ----
    match_features = ["range_pos_60", "realized_vol_30"]
    match_rows = []
    for idx_name, idx_feats, idx_bars in [("QQQ", qqq_feats, qqq), ("SPY", spy_feats, spy)]:
        idx_valid = idx_feats[match_features].dropna()
        if len(idx_valid) == 0:
            continue
        idx_z = (idx_valid - idx_valid.mean()) / idx_valid.std()
        for sym_name, h_feats, h_full_feats, sym_bars, sym_trades in [
            ("BTCUSDT", btc_h_feats, btc_feats, btc, trades[trades["symbol"] == "BTCUSDT"]),
            ("ETHUSDT", eth_h_feats, eth_feats, eth, trades[trades["symbol"] == "ETHUSDT"]),
        ]:
            crypto_mean, crypto_std = h_full_feats[match_features].mean(), h_full_feats[match_features].std()
            sample = h_feats[match_features].dropna().sample(n=min(20, len(h_feats.dropna())), random_state=0) if len(h_feats.dropna()) else pd.DataFrame()
            for entry_time, feat_row in sample.iterrows():
                z = (feat_row - crypto_mean) / crypto_std
                dists = np.sqrt(((idx_z - z) ** 2).sum(axis=1))
                nearest_ts = dists.idxmin()
                nearest_dist = float(dists.min())
                pos = idx_bars.index.get_indexer([nearest_ts])[0]
                if pos < 0 or pos + 30 >= len(idx_bars):
                    continue
                entry_px = idx_bars["close"].iloc[pos]
                fwd30 = idx_bars["close"].iloc[pos:pos + 31].to_numpy() / entry_px - 1.0
                trade_row = sym_trades[sym_trades["entry_time"] == entry_time]
                crypto_mfe = np.nan
                if len(trade_row):
                    path = np.array([float(x) for x in trade_row.iloc[0]["close_path"].split(";")])
                    crypto_mfe = float(path[:31].max())
                match_rows.append({"crypto_symbol": sym_name, "crypto_entry_time": str(entry_time),
                                    "index": idx_name, "matched_index_time": str(nearest_ts),
                                    "match_distance_z": nearest_dist, "crypto_mfe_30m": crypto_mfe,
                                    "index_mfe_30m": float(fwd30.max()), "index_mae_30m": float(fwd30.min())})
    match_df = pd.DataFrame(match_rows)
    match_path = os.path.join(MECH2_DOCS, "strategy_a_matched_event_test.csv")
    match_df.to_csv(match_path, index=False)
    print(f"Saved -> {match_path} ({len(match_df)} rows)")


if __name__ == "__main__":
    main()
