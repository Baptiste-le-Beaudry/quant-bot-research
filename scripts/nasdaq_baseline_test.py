"""
scripts/nasdaq_baseline_test.py — Multi-asset expansion plan, Phase 2 (the
user's own flagged "most important step"): apply BASELINE_CANDIDATE_V3's
exact strategy UNCHANGED (same model architecture/features/horizon=10min/
threshold=0.70/range_pos_60+realized_vol_30 filter/trailing 0.63%+0.80%/
p90 protective stop/dynamic leverage formula) to Nasdaq 100 (Dukascopy
USATECH.IDX-USD, docs/dukascopy_data_access.md memory note), recalibrating
ONLY the TRAIN-derived statistics (filter cutoffs, stop distance) from
Nasdaq's own TRAIN split -- explicitly NOT reusing any BTC/ETH numeric
cutoffs. This answers Phase 7's real question first: does this edge show
up on Nasdaq at all before any market-specific adaptation (ATR-normalized
features, session awareness, ATR-scaled trailing, etc. -- Phases 3-4,
deferred until this unchanged-baseline result is in hand)?

60/20/20 TRAIN/VALIDATION/HOLDOUT split (fresh for this market, HOLDOUT
untouched here). Single fixed-split evaluation (not walk-forward yet) --
matches how the crypto baseline was originally screened before its own
walk-forward treatment.

Usage:
    python scripts/nasdaq_baseline_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd

from quant_bot.config import COST_THRESHOLD_PCT, ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST, TAKER_FEE_PCT
from quant_bot.features.build import build_feature_matrix, build_labels
from quant_bot.features.pipeline import prune_redundant
from quant_bot.signal.model import Tier2RandomForestSignal
from scripts.diagnostic_leverage import STOP_OUT_FRACTION
from scripts.mae_mfe_analysis import build_trades_with_mae_mfe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
_parser = argparse.ArgumentParser()
_parser.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "..", "data", "indices", "NASDAQ100_1m.csv"))
_parser.add_argument("--label", default="NASDAQ 100 (USATECH.IDX-USD)")
_parser.add_argument("--scale-trail", action="store_true",
                      help="Phase 10 test: scale ACTIVATE_AT/TRAIL_DIST proportionally to this "
                           "market's OWN TRAIN-calibrated stop_distance instead of reusing crypto's "
                           "fixed absolute 0.63%%/0.80%%. Ratios (18%%/23%% of stop_distance) come from "
                           "V3's own crypto stop_distance ~3.5%% (0.63/3.5=18%%, 0.80/3.5=23%%).")
_parser.add_argument("--exclude-post-gap", type=int, default=0,
                      help="Phase 4 test: exclude entries within N bars of a session gap >10min "
                           "(this market has a real ~112min daily close, contaminating naive "
                           "ret_1/realized_vol_30 for a window after each reopen). 0 = disabled.")
_parser.add_argument("--percentile-features", action="store_true",
                      help="Phase 3 test: add a causal rolling-percentile-rank version of "
                           "realized_vol_30 (market-relative 'how volatile is RIGHT NOW vs this "
                           "market's own recent history', not an absolute number) as an extra "
                           "model feature AND swap it in for the raw-value filter cutoff.")
_args, _ = _parser.parse_known_args()
DATA_PATH = _args.data
MARKET_LABEL = _args.label
SCALE_TRAIL = _args.scale_trail
EXCLUDE_POST_GAP = _args.exclude_post_gap
PERCENTILE_FEATURES = _args.percentile_features
VOL_PCTILE_WINDOW = 4320  # 3 days of 1-min bars -- causal (backward-looking only), no leakage
ACTIVATE_RATIO, TRAIL_RATIO = 0.18, 0.23  # only used if SCALE_TRAIL
TRAIN_FRACTION, VALIDATION_FRACTION = 0.60, 0.20
HORIZON = 10          # UNCHANGED from V3
EXTENSION_CAP = 40    # UNCHANGED from V3
LOOKAHEAD = HORIZON + EXTENSION_CAP
THRESHOLD = 0.70       # UNCHANGED from V3
ACTIVATE_AT = 0.0063   # UNCHANGED from V3 -- deliberately NOT ATR-scaled yet (that's Phase 10)
TRAIL_DIST = 0.0080    # UNCHANGED from V3
STOP_PCT_PERCENTILE = 90
SAFETY_MARGIN = 0.75
MAX_LEVERAGE_CAP = 30.0
FEE_PER_SIDE = TAKER_FEE_PCT
BASE_SLIP_PER_SIDE = SLIPPAGE_PCT_EST / 2.0
CAPITAL = 10_000.0
RISK_PCT = 0.01


def load_split(split: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, index_col=0, parse_dates=True)
    # Dukascopy's aggregated OHLCV has no buy/sell split (unlike Binance futures klines);
    # build_feature_matrix expects taker_buy_volume/taker_sell_volume to exist. Neutral 50/50
    # split makes taker_imbalance_20 a constant/uninformative 0 rather than crashing -- this ONE
    # feature is simply not available for this market, everything else in the pipeline is
    # untouched (Phase 2's whole point: same code, same features where possible).
    df["taker_buy_volume"] = df["volume"] / 2.0
    df["taker_sell_volume"] = df["volume"] / 2.0
    n = len(df)
    train_end = int(n * TRAIN_FRACTION)
    val_end = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))
    bounds = {"train": (0, train_end), "validation": (train_end, val_end), "holdout": (val_end, n)}
    start, end = bounds[split]
    return df.iloc[start:end]


def add_percentile_features(feats: pd.DataFrame) -> pd.DataFrame:
    """Causal (backward-looking only) rolling-percentile-rank of realized_vol_30 -- 'is current
    volatility high or low RELATIVE TO THIS MARKET'S OWN recent history', market-scale-invariant
    by construction, unlike the raw absolute value. Also a z-scored ret_1 (return/volatility)."""
    feats = feats.copy()
    feats["vol_pctile"] = feats["realized_vol_30"].rolling(VOL_PCTILE_WINDOW, min_periods=500).rank(pct=True)
    feats["ret_1_z"] = feats["ret_1"] / feats["realized_vol_30"].replace(0, np.nan)
    return feats


def post_gap_mask(index: pd.DatetimeIndex, n_bars: int, gap_threshold_min: int = 10) -> np.ndarray:
    """True where a bar is CONTAMINATED (within n_bars of a session gap > gap_threshold_min)."""
    if n_bars <= 0:
        return np.zeros(len(index), dtype=bool)
    deltas_min = index.to_series().diff().dt.total_seconds().to_numpy() / 60.0
    is_gap = deltas_min > gap_threshold_min
    mask = np.zeros(len(index), dtype=bool)
    gap_positions = np.where(is_gap)[0]
    for pos in gap_positions:
        mask[pos:pos + n_bars] = True
    return mask


def resolve(entry_price, close_arr, i, stop_distance, leverage):
    path = close_arr[i:i + LOOKAHEAD + 1] / entry_price - 1.0
    liq_move = STOP_OUT_FRACTION / leverage
    protective = min(stop_distance, liq_move)
    peak, activated = -np.inf, False
    for x in path:
        if x <= -protective:
            return -protective - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
        if x > peak:
            peak = x
        if not activated and peak >= ACTIVATE_AT:
            activated = True
        if activated:
            stop_level = peak - TRAIL_DIST
            if x <= stop_level:
                return stop_level - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2
    return path[-1] - (FEE_PER_SIDE + BASE_SLIP_PER_SIDE) * 2


def main():
    print(f"Loading {MARKET_LABEL} from {DATA_PATH} ...")
    train_df = load_split("train")
    val_df = load_split("validation")
    print(f"TRAIN: {len(train_df):,} bars [{train_df.index[0]} -> {train_df.index[-1]}]")
    print(f"VALIDATION: {len(val_df):,} bars [{val_df.index[0]} -> {val_df.index[-1]}]")

    print("\nBuilding features + fitting Tier2RandomForestSignal on Nasdaq's OWN TRAIN only ...")
    train_feats = build_feature_matrix(train_df)
    if PERCENTILE_FEATURES:
        train_feats = add_percentile_features(train_feats)
        print(f"--percentile-features: added vol_pctile (rolling {VOL_PCTILE_WINDOW}-bar percentile "
              f"rank of realized_vol_30) and ret_1_z (ret_1/realized_vol_30)")
    train_labels = build_labels(train_df["close"], HORIZON, COST_THRESHOLD_PCT, direction="long")
    kept, _ = prune_redundant(train_feats, train_labels, corr_threshold=0.9)
    fit_n = min(250_000, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = Tier2RandomForestSignal(kept, n_estimators=100).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    print(f"{len(kept)} features kept.")

    train_proba = model.predict_proba(train_feats)
    train_selected = train_proba > THRESHOLD
    print(f"\nTRAIN-selected (proba>{THRESHOLD}) population: {train_selected.sum():,} / {len(train_feats):,}")
    if train_selected.sum() < 20:
        print("Too few TRAIN-selected bars to calibrate the entry filter -- STOPPING (Nasdaq-specific finding).")
        return

    vol_col = "vol_pctile" if PERCENTILE_FEATURES else "realized_vol_30"
    range_pos_cut = train_feats.loc[train_selected, "range_pos_60"].median()
    vol_cut = train_feats.loc[train_selected, vol_col].median()
    print(f"Nasdaq-own TRAIN cutoffs: range_pos_60 < {range_pos_cut:.4f}, {vol_col} > {vol_cut:.6f}")

    train_close = train_df["close"].to_numpy()
    train_filtered = (
        train_selected
        & (train_feats["range_pos_60"] < range_pos_cut)
        & (train_feats[vol_col] > vol_cut)
    ).to_numpy()
    if EXCLUDE_POST_GAP:
        gap_mask = post_gap_mask(train_df.index, EXCLUDE_POST_GAP)
        train_filtered = train_filtered & ~gap_mask
        print(f"--exclude-post-gap={EXCLUDE_POST_GAP}: excluded {gap_mask.sum():,} TRAIN bars "
              f"({gap_mask.mean()*100:.2f}%) as post-gap-contaminated")
    train_ema_slope = train_feats["ema_slope_20"].to_numpy()
    train_ret_1 = train_feats["ret_1"].to_numpy()
    train_trades = build_trades_with_mae_mfe(train_close, train_filtered, train_ema_slope, train_ret_1)
    print(f"TRAIN entries after filter: {len(train_trades)}")
    if len(train_trades) < 10:
        print("Too few TRAIN entries to calibrate the protective stop -- STOPPING (Nasdaq-specific finding).")
        return

    stop_distance = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop_distance, MAX_LEVERAGE_CAP)
    print(f"Nasdaq-own TRAIN p90 stop_distance={stop_distance*100:.2f}%  ->  dynamic leverage={leverage:.2f}x")

    global ACTIVATE_AT, TRAIL_DIST
    if SCALE_TRAIL:
        ACTIVATE_AT = ACTIVATE_RATIO * stop_distance
        TRAIL_DIST = TRAIL_RATIO * stop_distance
        print(f"--scale-trail: ACTIVATE_AT={ACTIVATE_AT*100:.3f}%  TRAIL_DIST={TRAIL_DIST*100:.3f}% "
              f"(scaled to this market's own stop, vs crypto's fixed 0.63%/0.80%)")

    print("\nApplying to VALIDATION (unseen) ...")
    val_feats = build_feature_matrix(val_df)
    if PERCENTILE_FEATURES:
        val_feats = add_percentile_features(val_feats)
    val_proba = model.predict_proba(val_feats)
    val_filtered = (
        (val_proba > THRESHOLD)
        & (val_feats["range_pos_60"] < range_pos_cut)
        & (val_feats[vol_col] > vol_cut)
    ).to_numpy()
    if EXCLUDE_POST_GAP:
        val_gap_mask = post_gap_mask(val_df.index, EXCLUDE_POST_GAP)
        val_filtered = val_filtered & ~val_gap_mask
        print(f"--exclude-post-gap={EXCLUDE_POST_GAP}: excluded {val_gap_mask.sum():,} VALIDATION bars "
              f"({val_gap_mask.mean()*100:.2f}%) as post-gap-contaminated")
    val_close = val_df["close"].to_numpy()
    n_val = len(val_close)

    notional = CAPITAL * RISK_PCT
    pnls = []
    i = 0
    while i < n_val - LOOKAHEAD - 1:
        if not val_filtered[i]:
            i += 1
            continue
        ret = resolve(val_close[i], val_close, i, stop_distance, leverage)
        pnls.append(ret * notional * leverage)
        i += HORIZON

    if not pnls:
        print("No VALIDATION entries -- Nasdaq produces ZERO trades under the unchanged V3 rule.")
        return

    pnls = np.array(pnls)
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    win_rate = (pnls > 0).mean() * 100
    total_ret_pct = pnls.sum() / CAPITAL * 100
    eq = CAPITAL + np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))
    dd = (np.concatenate([[CAPITAL], eq]) - running_max) / running_max
    n_days = (val_df.index[-1] - val_df.index[0]).days
    cagr = ((eq[-1] / CAPITAL) ** (365.25 / max(n_days, 1)) - 1) * 100 if eq[-1] > 0 else float("nan")

    print("\n" + "=" * 90)
    print(f"  {MARKET_LABEL} -- BASELINE_CANDIDATE_V3, UNCHANGED, VALIDATION result")
    print("=" * 90)
    print(f"  n_trades={len(pnls)}  PF={pf:.3f}  win_rate={win_rate:.1f}%  "
          f"total_return={total_ret_pct:+.2f}%  MaxDD={dd.min()*100:.2f}%  "
          f"CAGR={cagr:+.2f}%  leverage={leverage:.2f}x  stop={stop_distance*100:.2f}%")
    print(f"\n  Reference (BASELINE_CANDIDATE_V3 walk-forward, Experiment 28):")
    print(f"    BTC:  n=211  median_PF=1.628  |  ETH: n=333  median_PF=1.300")


if __name__ == "__main__":
    main()
