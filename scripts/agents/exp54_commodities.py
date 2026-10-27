"""Exp 54 (A-COMMOD-001) -- intraday dip-buy on metals/energy, executable exits.

Pre-registration: docs/agents/hypotheses/Exp-54.md (commit 55bbb51). Nothing
here is tuned; every constant below is either copied from configuration D
(scripts/strategy_a_equity/own_asset_walkforward.py) or fixed by the spec.

Reused unchanged from configuration D: build_feature_matrix, build_labels
(HORIZON=10), prune_redundant(corr_threshold=0.9), the two models via
own_asset_walkforward.make_model (RF n_estimators=100 / logistic), the
250k-row fit sample (random_state=42), the TRAIN top-decile gate
(SELECTION_QUANTILE=0.90), the range_pos_60/realized_vol_30 median filter
on the gated TRAIN rows, the population guards (gated TRAIN rows >= 20,
TRAIN trades >= 10 via build_trades_with_mae_mfe).

Exp-54-specific (spec):
  * label cost = median (ASK close - BID close)/BID close on the fold's TRAIN;
  * walk-forward: expanding TRAIN from the first bar, TEST 3 months, step
    3 months, first TRAIN >= 36 months (first train_end = first calendar
    quarter start >= first bar + 36 months), last test_end <= 2025-10-01;
  * execution: signal at the close of bar s, entry at the ASK open of bar
    s+1, exit at the BID close of bar s+50 (50 bars held, positional --
    same convention as harness v1 ExitRule(max_bars=50), no stop), one
    position at a time, no entry unless bars s..s+50 belong to the same
    trading session; commission 0 and 0.005 %/side.

Deviations forced by feasibility (documented in the report):
  * features are computed ONCE per instrument on the full pre-HOLDOUT
    series (causal rolling/EWM features => TRAIN slices are bit-identical
    to a per-fold recomputation since TRAIN always starts at the first bar;
    TEST features carry their real history instead of a cold start).
  * session = maximal run of bars whose consecutive gap is <= 30 minutes
    (data: every systematic closure -- daily break, weekends, holidays --
    is >= 60 min; intra-session illiquidity gaps are almost all <= 20 min).

HOLDOUT (>= 2025-10-01) is dropped at load time and asserted.

Usage:
    python scripts/agents/exp54_commodities.py prepare --inst XAUUSD
    python scripts/agents/exp54_commodities.py run --inst XAUUSD --model rf
    python scripts/agents/exp54_commodities.py aggregate
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from quant_bot.features.build import build_feature_matrix, build_labels  # noqa: E402
from quant_bot.features.pipeline import prune_redundant  # noqa: E402
from scripts.fast_trades import build_trades_with_mae_mfe_fast as build_trades_with_mae_mfe  # noqa: E402
from scripts.strategy_a_equity import own_asset_walkforward as oaw  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---- fixed by the pre-registration -------------------------------------
INSTRUMENTS = ("XAUUSD", "XAGUSD", "WTI", "BRENT", "COPPER", "GAS")
MODELS = ("rf", "logistic")
COMMISSIONS = {"c0": 0.0, "c0005": 0.00005}  # per side: 0 and 0.005 %
HOLDOUT_START = pd.Timestamp("2025-10-01", tz="UTC")
MIN_TRAIN_MONTHS = 36
TEST_MONTHS = STEP_MONTHS = 3
HOLD_BARS = 50
NOTIONAL_FRACTION = 0.33
# ---- copied from configuration D (own_asset_walkforward.py) -------------
HORIZON = oaw.HORIZON                    # 10
SELECTION_QUANTILE = oaw.SELECTION_QUANTILE  # 0.90
FIT_ROWS = 250_000
# ---- data-derived session definition -------------------------------------
SESSION_GAP_MIN = 30

DATA_ROOT = Path(os.environ.get("EXP54_DATA_ROOT", "C:/AAProjet/quant_bot_v1/data/commodities"))
OUT_DIR = REPO / "docs" / "agents" / "results" / "exp54"


# ------------------------------------------------------------------ data
def load_instrument(name: str, raw_root: Path | None = None) -> pd.DataFrame:
    """BID OHLCV + ASK open/close, inner-joined, HOLDOUT rows dropped."""
    raw_root = raw_root or DATA_ROOT / "raw"
    sides = {}
    for side in ("BID", "ASK"):
        files = sorted(glob.glob(str(raw_root / f"{name}_{side}" / "*.pkl")))
        # month files are named YYYY-MM.pkl: never even open a HOLDOUT month
        files = [f for f in files if Path(f).stem < HOLDOUT_START.strftime("%Y-%m")]
        if not files:
            raise FileNotFoundError(f"no {side} data for {name} under {raw_root}")
        df = pd.concat([pd.read_pickle(f) for f in files]).sort_index()
        df = df[~df.index.duplicated(keep="first")]
        df = df[df.index < HOLDOUT_START]
        sides[side] = df
    bid, ask = sides["BID"], sides["ASK"]
    out = bid[["open", "high", "low", "close", "volume"]].astype(float).copy()
    out["taker_buy_volume"] = out["volume"] / 2.0   # same disclosed convention as A-Equity
    out["taker_sell_volume"] = out["volume"] / 2.0
    out = out.join(ask[["open", "close"]].astype(float).add_prefix("ask_"), how="inner")
    assert out.index.max() < HOLDOUT_START, "HOLDOUT bar leaked into modelling data"
    assert out.index.is_monotonic_increasing
    return out


def session_ids(index: pd.DatetimeIndex, gap_min: int = SESSION_GAP_MIN) -> np.ndarray:
    gaps = index.to_series().diff().dt.total_seconds().div(60).to_numpy()
    return np.cumsum(np.nan_to_num(gaps, nan=0.0) > gap_min)


def build_folds(first_bar: pd.Timestamp, end: pd.Timestamp = HOLDOUT_START):
    min_end = first_bar + pd.DateOffset(months=MIN_TRAIN_MONTHS)
    q = pd.Timestamp(year=min_end.year, month=1 + 3 * ((min_end.month - 1) // 3), day=1, tz="UTC")
    train_end = q if q >= min_end else q + pd.DateOffset(months=3)
    folds = []
    while True:
        test_end = train_end + pd.DateOffset(months=TEST_MONTHS)
        if test_end > end:
            break
        folds.append((first_bar, train_end, test_end))
        train_end = train_end + pd.DateOffset(months=STEP_MONTHS)
    return folds


def cache_paths(name: str):
    c = DATA_ROOT / "cache"
    return c / f"{name}_bars.pkl", c / f"{name}_features.pkl"


def prepare(name: str):
    bars_p, feats_p = cache_paths(name)
    bars_p.parent.mkdir(parents=True, exist_ok=True)
    if bars_p.exists() and feats_p.exists():
        print(f"{name}: cache exists")
        return
    t = time.time()
    df = load_instrument(name)
    feats = build_feature_matrix(df[["open", "high", "low", "close", "volume",
                                     "taker_buy_volume", "taker_sell_volume"]])
    assert feats.index.max() < HOLDOUT_START
    df.to_pickle(bars_p)
    feats.to_pickle(feats_p)
    print(f"{name}: {len(df):,} bars {df.index[0]} -> {df.index[-1]}, features in {time.time() - t:.0f}s")


# ------------------------------------------------------------- execution
def simulate(ask_open: np.ndarray, bid_close: np.ndarray, bid_high: np.ndarray, bid_low: np.ndarray,
             sess: np.ndarray, signal_mask: np.ndarray, lo: int, hi: int, hold: int = HOLD_BARS):
    """Sequential, one position at a time. Signals s in [lo, hi); exit bar
    s+hold must be < hi (inside the TEST fold) and in the same session as s.
    Entry = ask_open[s+1]; exit = bid_close[s+hold]. Returns list of dicts."""
    trades = []
    next_free = lo
    for s in np.flatnonzero(signal_mask[lo:hi]) + lo:
        if s < next_free:
            continue
        e = s + hold
        if e >= hi or sess[s] != sess[e]:
            continue
        entry = ask_open[s + 1]
        exit_ = bid_close[e]
        trades.append({
            "signal_idx": int(s), "entry_idx": int(s + 1), "exit_idx": int(e),
            "entry_ask": float(entry), "exit_bid": float(exit_),
            "ret_spread": float(exit_ / entry - 1.0),
            "mfe": float(bid_high[s + 1:e + 1].max() / entry - 1.0),
            "mae": float(bid_low[s + 1:e + 1].min() / entry - 1.0),
        })
        next_free = e  # signal at the close of the exit bar may re-enter at the next open
    return trades


def profit_factor(r: np.ndarray) -> float:
    r = np.asarray(r, float)
    if len(r) == 0:
        return float("nan")
    loss = -r[r <= 0].sum()
    return float(r[r > 0].sum() / loss) if loss > 0 else float("inf")


# ------------------------------------------------------------------ fold
def fit_model(train_feats: pd.DataFrame, train_close: pd.Series, label_cost: float, model_name: str):
    """Body of own_asset_walkforward.fit_fold_model, with precomputed
    (causal, bit-identical) TRAIN features and the TRAIN-measured cost."""
    train_labels = build_labels(train_close, HORIZON, label_cost, direction="long")
    kept, _ = prune_redundant(train_feats, train_labels, corr_threshold=0.9)
    fit_n = min(FIT_ROWS, len(train_feats))
    fit_idx = train_feats.sample(n=fit_n, random_state=42).index
    model = oaw.make_model(model_name, kept).fit(train_feats.loc[fit_idx], train_labels.loc[fit_idx])
    return model, kept, train_labels


def process_fold(name, model_name, fold_i, bars, feats, sess, t0, train_end, test_end):
    idx = bars.index
    a = int(idx.searchsorted(t0, side="left"))
    b = int(idx.searchsorted(train_end, side="left"))
    c = int(idx.searchsorted(test_end, side="left"))
    assert a == 0
    tr_bars, tr_feats = bars.iloc[a:b], feats.iloc[a:b]
    assert tr_bars.index.max() < train_end <= bars.index[b]
    info = {"inst": name, "model": model_name, "fold": fold_i, "train_start": str(t0),
            "train_end": str(train_end), "test_end": str(test_end),
            "train_n": b - a, "test_n": c - b}

    spread = (tr_bars["ask_close"] - tr_bars["close"]) / tr_bars["close"]
    label_cost = float(spread.median())
    info["label_cost_train_median_spread"] = label_cost

    model, kept, _ = fit_model(tr_feats, tr_bars["close"], label_cost, model_name)
    info["n_features_kept"] = len(kept)
    train_proba = model.predict_proba(tr_feats)
    valid = train_proba.dropna()
    if len(valid) < 20:
        return {**info, "n_trades": 0, "skip": "TRAIN scores unavailable"}, []
    cut = float(valid.quantile(SELECTION_QUANTILE))
    gate = train_proba > cut
    info["selection_cut"] = cut
    if gate.sum() < 20:
        return {**info, "n_trades": 0, "skip": "TRAIN population too small after topdecile cut"}, []
    rp_cut = tr_feats.loc[gate, "range_pos_60"].median()
    vol_cut = tr_feats.loc[gate, "realized_vol_30"].median()
    train_mask = gate & (tr_feats["range_pos_60"] < rp_cut) & (tr_feats["realized_vol_30"] > vol_cut)
    info.update(range_pos_cut=float(rp_cut), vol_cut=float(vol_cut))
    train_trades = build_trades_with_mae_mfe(
        tr_bars["close"].to_numpy(), train_mask.to_numpy(),
        tr_feats["ema_slope_20"].to_numpy(), tr_feats["ret_1"].to_numpy(), horizon=HORIZON)
    if len(train_trades) < 10:
        return {**info, "n_trades": 0, "skip": "TRAIN trade population too small"}, []

    te_feats = feats.iloc[b:c]
    te_proba = model.predict_proba(te_feats)
    sig = ((te_proba > cut) & (te_feats["range_pos_60"] < rp_cut)
           & (te_feats["realized_vol_30"] > vol_cut)).to_numpy()
    signal_mask = np.zeros(len(bars), dtype=bool)
    signal_mask[b:c] = sig
    info["n_signals"] = int(sig.sum())
    trades = simulate(bars["ask_open"].to_numpy(), bars["close"].to_numpy(), bars["high"].to_numpy(),
                      bars["low"].to_numpy(), sess, signal_mask, b, c)

    # generic (every session-valid bar, overlapping) MFE/MAE baseline on the same TEST window
    rows = []
    for t in trades:
        s, e = t["signal_idx"], t["exit_idx"]
        rows.append({
            "inst": name, "model": model_name, "fold": fold_i,
            "signal_time": idx[s], "entry_time": idx[s + 1], "exit_time": idx[e],
            "entry_ask": t["entry_ask"], "exit_bid": t["exit_bid"],
            "entry_bid_open": float(bars["open"].iat[s + 1]),
            "exit_ask_close": float(bars["ask_close"].iat[e]),
            "ret_net_c0": t["ret_spread"] - 2 * COMMISSIONS["c0"],
            "ret_net_c0005": t["ret_spread"] - 2 * COMMISSIONS["c0005"],
            "ret_mid": ((bars["close"].iat[e] + bars["ask_close"].iat[e]) /
                        (bars["open"].iat[s + 1] + bars["ask_open"].iat[s + 1]) - 1.0),
            "mfe": t["mfe"], "mae": t["mae"],
            "hold_minutes": (idx[e] - idx[s + 1]).total_seconds() / 60 + 1,
            "gap_in_window": bool((idx[e] - idx[s + 1]).total_seconds() / 60 != HOLD_BARS - 1),
        })
    tr = pd.DataFrame(rows)
    summ = {**info, "n_trades": len(tr), "skip": ""}
    if len(tr):
        for k in COMMISSIONS:
            r = tr[f"ret_net_{k}"].to_numpy()
            summ[f"pf_{k}"] = profit_factor(r)
            summ[f"mean_{k}"] = float(r.mean())
            summ[f"win_{k}"] = float((r > 0).mean())
        summ["mean_ret_mid"] = float(tr["ret_mid"].mean())
        summ["mean_entry_spread"] = float(((tr["entry_ask"] - tr["entry_bid_open"]) / tr["entry_bid_open"]).mean())
        summ["mfe_mean"] = float(tr["mfe"].mean())
        summ["mae_mean"] = float(tr["mae"].abs().mean())
        summ["gap_in_window_share"] = float(tr["gap_in_window"].mean())
    return summ, rows


def fold_paths(name, model_name, fold_i):
    d = OUT_DIR / "folds"
    return d / f"{name}_{model_name}_f{fold_i:02d}_summary.json", d / f"{name}_{model_name}_f{fold_i:02d}_trades.csv"


def run(name: str, model_name: str, max_folds: int | None = None):
    bars_p, feats_p = cache_paths(name)
    bars = pd.read_pickle(bars_p)
    feats = pd.read_pickle(feats_p)
    assert bars.index.max() < HOLDOUT_START and feats.index.max() < HOLDOUT_START
    assert bars.index.equals(feats.index)
    sess = session_ids(bars.index)
    folds = build_folds(bars.index[0])
    (OUT_DIR / "folds").mkdir(parents=True, exist_ok=True)
    print(f"[{name}/{model_name}] {len(folds)} folds, first TEST {folds[0][1]:%Y-%m-%d}", flush=True)
    done = 0
    for i, (t0, tr_end, te_end) in enumerate(folds, 1):
        sp, tp = fold_paths(name, model_name, i)
        if sp.exists():
            continue
        if max_folds is not None and done >= max_folds:
            break
        t = time.time()
        summ, rows = process_fold(name, model_name, i, bars, feats, sess, t0, tr_end, te_end)
        pd.DataFrame(rows).to_csv(tp, index=False)
        tmp = sp.with_suffix(".tmp")
        tmp.write_text(json.dumps(summ, default=str, indent=1))
        tmp.replace(sp)
        done += 1
        print(f"  {name}/{model_name} fold {i:02d} TEST {tr_end:%Y-%m} n={summ['n_trades']} "
              f"pf_c0005={summ.get('pf_c0005', float('nan')):.3f} {summ.get('skip', '')} "
              f"({time.time() - t:.0f}s)", flush=True)


# ------------------------------------------------------------- aggregate
def aggregate():
    fdir = OUT_DIR / "folds"
    summaries = [json.loads(Path(p).read_text()) for p in sorted(glob.glob(str(fdir / "*_summary.json")))]
    S = pd.DataFrame(summaries)
    trade_files = [p for p in sorted(glob.glob(str(fdir / "*_trades.csv"))) if os.path.getsize(p) > 2]
    T = pd.concat([pd.read_csv(p, parse_dates=["signal_time", "entry_time", "exit_time"]) for p in trade_files],
                  ignore_index=True) if trade_files else pd.DataFrame()
    assert len(T) == 0 or pd.to_datetime(T["exit_time"]).max() < HOLDOUT_START
    S.to_csv(OUT_DIR / "exp54_folds.csv", index=False)
    T.to_csv(OUT_DIR / "exp54_trades.csv", index=False)

    rows = []
    for (inst, model), g in S.groupby(["inst", "model"]):
        ti = T[(T.inst == inst) & (T.model == model)] if len(T) else T
        oos_start = pd.Timestamp(g["train_end"].min())
        oos_end = pd.Timestamp(g["test_end"].max())
        years = (oos_end - oos_start).days / 365.25
        for k, comm in COMMISSIONS.items():
            traded = g[g.n_trades > 0]
            pf_folds = traded[f"pf_{k}"].astype(float)
            r = ti[f"ret_net_{k}"].to_numpy() if len(ti) else np.array([])
            eq = np.cumprod(1 + NOTIONAL_FRACTION * r) if len(r) else np.array([1.0])
            daily = (ti.assign(d=pd.to_datetime(ti.exit_time).dt.date, x=NOTIONAL_FRACTION * ti[f"ret_net_{k}"])
                     .groupby("d").x.sum()) if len(ti) else pd.Series(dtype=float)
            peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))
            rows.append({
                "inst": inst, "model": model, "commission": k, "commission_per_side": comm,
                "n_folds": len(g), "n_folds_traded": len(traded), "n_folds_skipped": int((g.get("skip", "") != "").sum()),
                "n_trades": len(r), "trades_per_year": len(r) / years if years else np.nan,
                "oos_start": str(oos_start.date()), "oos_end": str(oos_end.date()),
                "median_fold_pf": float(pf_folds.median()) if len(pf_folds) else np.nan,
                "share_folds_pf_gt1_all": float((pf_folds > 1).sum() / len(g)),
                "share_folds_pf_gt1_traded": float((pf_folds > 1).mean()) if len(pf_folds) else np.nan,
                "pooled_pf": profit_factor(r), "mean_net": float(r.mean()) if len(r) else np.nan,
                "std_net": float(r.std(ddof=1)) if len(r) > 1 else np.nan,
                "win_rate": float((r > 0).mean()) if len(r) else np.nan,
                "mean_mid_gross": float(ti["ret_mid"].mean()) if len(ti) else np.nan,
                "mean_entry_spread": float(((ti.entry_ask - ti.entry_bid_open) / ti.entry_bid_open).mean()) if len(ti) else np.nan,
                "mfe_mean": float(ti["mfe"].mean()) if len(ti) else np.nan,
                "mae_abs_mean": float(ti["mae"].abs().mean()) if len(ti) else np.nan,
                "worst_day_33pct": float(daily.min()) if len(daily) else np.nan,
                "total_return_33pct": float(eq[-1] - 1.0),
                "cagr_33pct": float(eq[-1] ** (1 / years) - 1.0) if years and eq[-1] > 0 else np.nan,
                "max_dd_33pct": float((np.concatenate([[1.0], eq]) / peak - 1).min()),
                "gap_in_window_share": float(ti["gap_in_window"].mean()) if len(ti) else np.nan,
            })
    R = pd.DataFrame(rows)
    R.to_csv(OUT_DIR / "exp54_configs.csv", index=False)

    # instrument pass: both models, commission 0.005 %/side
    inst_rows = []
    for inst, g in R[R.commission == "c0005"].groupby("inst"):
        ok = {m: bool((x.median_fold_pf.iloc[0] > 1) and (x.share_folds_pf_gt1_all.iloc[0] >= 0.5))
              for m, x in g.groupby("model")}
        ok_traded = {m: bool((x.median_fold_pf.iloc[0] > 1) and (x.share_folds_pf_gt1_traded.iloc[0] >= 0.5))
                     for m, x in g.groupby("model")}
        inst_rows.append({"inst": inst, **{f"pass_{m}": v for m, v in ok.items()},
                          "instrument_pass": all(ok.values()) and len(ok) == 2,
                          "instrument_pass_traded_denominator": all(ok_traded.values()) and len(ok_traded) == 2})
    I = pd.DataFrame(inst_rows)
    I.to_csv(OUT_DIR / "exp54_instrument_pass.csv", index=False)

    # pooled mean net per trade by chronological half (calendar midpoint of the OOS span)
    halves = []
    if len(T):
        oos_start = pd.Timestamp(S["train_end"].min())
        mid = oos_start + (HOLDOUT_START - oos_start) / 2
        T["half"] = np.where(pd.to_datetime(T.entry_time) < mid, "H1", "H2")
        for k in COMMISSIONS:
            for scope, sub in [("all", T)] + [(m, T[T.model == m]) for m in MODELS]:
                for h in ("H1", "H2"):
                    x = sub[sub.half == h][f"ret_net_{k}"]
                    halves.append({"commission": k, "scope": scope, "half": h, "midpoint": str(mid),
                                   "n": len(x), "mean_net": float(x.mean()) if len(x) else np.nan,
                                   "se": float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan})
    H = pd.DataFrame(halves)
    H.to_csv(OUT_DIR / "exp54_pooled_halves.csv", index=False)

    # worst day, 6 instruments together at 33 % each (gross up to 198 %), per model
    port = []
    if len(T):
        for k in COMMISSIONS:
            for m in MODELS:
                sub = T[T.model == m]
                d = sub.assign(d=pd.to_datetime(sub.exit_time).dt.date,
                               x=NOTIONAL_FRACTION * sub[f"ret_net_{k}"]).groupby("d").x.sum()
                port.append({"commission": k, "model": m, "n": len(sub),
                             "worst_day_6inst_33pct": float(d.min()), "sum_simple_33pct": float(d.sum())})
    pd.DataFrame(port).to_csv(OUT_DIR / "exp54_portfolio_worst_day.csv", index=False)
    pd.set_option("display.width", 250)
    print(R.round(4).to_string(index=False))
    print(I.to_string(index=False))
    print(H.round(6).to_string(index=False))
    print(pd.DataFrame(port).round(4).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--inst", choices=INSTRUMENTS, required=True)
    r = sub.add_parser("run"); r.add_argument("--inst", choices=INSTRUMENTS, required=True)
    r.add_argument("--model", choices=MODELS, required=True); r.add_argument("--max-folds", type=int)
    sub.add_parser("aggregate")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.inst)
    elif a.cmd == "run":
        run(a.inst, a.model, a.max_folds)
    else:
        aggregate()


if __name__ == "__main__":
    main()
