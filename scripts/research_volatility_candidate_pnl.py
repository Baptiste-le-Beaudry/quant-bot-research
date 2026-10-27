"""Full exit/PnL validation for shortlisted volatility gates."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "strategy_a" / "mechanism2"))
from common import SYMBOLS_9, load_symbol, load_symbol_feats, get_folds, fold_layers, build_layer_trades
from scripts.multi_crypto_walkforward import resolve_stressed, STOP_PCT_PERCENTILE, SAFETY_MARGIN, MAX_LEVERAGE_CAP, STOP_OUT_FRACTION

OUT = ROOT / "outputs" / "crypto_volatility_research"
PATH = OUT / "candidate_pnl_full_1440.csv"
CANDIDATES = ("baseline_absolute", "regime_ratio_w1440_trainq75")

def variant_mask(name, feats, proba, train_feats, train_proba, range_cut, vol_cut):
    base = proba.gt(.70) & feats.range_pos_60.lt(range_cut)
    if name == "baseline_absolute":
        return base & feats.realized_vol_30.gt(vol_cut)
    if name == "no_vol_filter":
        return base
    window = int(name.split("_w")[1].split("_")[0])
    quantile = int(name.split("trainq")[1]) / 100
    ratio_train = train_feats.realized_vol_30 / train_feats.realized_vol_30.rolling(window, min_periods=max(60, window // 4)).median()
    selected = train_proba.gt(.70) & train_feats.range_pos_60.lt(range_cut)
    cut = float(ratio_train[selected].quantile(quantile))
    ratio_test = feats.realized_vol_30 / feats.realized_vol_30.rolling(window, min_periods=max(60, window // 4)).median()
    return base & ratio_test.gt(cut)

def score(trades, stop):
    if not trades:
        return {"n": 0, "pnl": 0.0, "return_pct": 0.0, "pf": np.nan, "max_dd_pct": 0.0, "winrate_pct": np.nan}
    leverage = min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop, MAX_LEVERAGE_CAP)
    protective = min(stop, STOP_OUT_FRACTION / leverage)
    pnls = np.asarray([resolve_stressed(t["close_path"], protective) * 10000 * .01 * leverage for t in trades])
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    equity = 10000 + np.cumsum(pnls)
    peak = np.maximum.accumulate(np.r_[10000, equity])
    return {"n": len(pnls), "pnl": float(pnls.sum()), "return_pct": float(pnls.sum() / 100),
            "pf": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.inf,
            "max_dd_pct": float(np.min((np.r_[10000, equity] - peak) / peak) * 100),
            "winrate_pct": float((pnls > 0).mean() * 100)}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    done = set()
    if PATH.exists():
        old = pd.read_csv(PATH); rows = old.to_dict("records"); done = set(zip(old.symbol, old.fold))
    for symbol in SYMBOLS_9:
        full = load_symbol(symbol); full_feats = load_symbol_feats(symbol, full); folds, _ = get_folds(full)
        for fold, (start, train_end, test_end) in enumerate(folds, 1):
            if (symbol, fold) in done: continue
            train = full[(full.index >= start) & (full.index < train_end)]
            test = full[(full.index >= train_end) & (full.index < test_end)]
            result = fold_layers(symbol, fold, train, test, full_feats=full_feats)
            if result is None: continue
            train_feats = result["train_feats"]; train_proba = result["model"].predict_proba(train_feats)
            test_feats = result["test_feats"]; test_proba = result["test_proba"]
            row = {"symbol": symbol, "fold": fold, "train_end": train_end, "test_end": test_end}
            for name in CANDIDATES:
                train_mask = variant_mask(name, train_feats, train_proba, train_feats, train_proba, result["range_pos_cut"], result["vol_cut"]).fillna(False)
                train_trades = build_layer_trades(result["test_close"] if False else train["close"].to_numpy(), train_mask, train_feats)
                if len(train_trades) < 10:
                    row[name + "__n"] = 0; continue
                stop = float(np.percentile(np.abs([t["mae"] for t in train_trades]), STOP_PCT_PERCENTILE))
                test_mask = variant_mask(name, test_feats, test_proba, train_feats, train_proba, result["range_pos_cut"], result["vol_cut"]).fillna(False)
                metrics = score(build_layer_trades(result["test_close"], test_mask, test_feats), stop)
                for key, value in metrics.items(): row[name + "__" + key] = value
            rows.append(row); pd.DataFrame(rows).to_csv(PATH, index=False); print(symbol, fold, "/", len(folds), "done")
    data = pd.DataFrame(rows); summary = []
    for name in CANDIDATES:
        n = data[name + "__n"].fillna(0).sum(); pf = data[name + "__pf"].replace(np.inf, np.nan).dropna()
        summary.append({"variant": name, "folds": len(data), "total_trades": int(n), "zero_trade_folds": int((data[name + "__n"].fillna(0) == 0).sum()), "total_pnl": data[name + "__pnl"].fillna(0).sum(), "sum_fold_return_pct": data[name + "__return_pct"].fillna(0).sum(), "median_fold_pf": pf.median(), "folds_pf_gt1": int((data[name + "__pf"] > 1).sum()), "median_fold_dd_pct": data[name + "__max_dd_pct"].median(), "weighted_winrate_pct": (data[name + "__winrate_pct"] * data[name + "__n"]).sum() / n if n else np.nan})
    pd.DataFrame(summary).to_csv(OUT / "candidate_pnl_full_1440_summary.csv", index=False); print(pd.DataFrame(summary).to_string(index=False))

if __name__ == "__main__": main()
