"""Refit the crypto Strategy-A bundle for the Jupiter paper run (SOL, BTC, ETH).

Same procedure as scripts/build_forward_strategy_a_bundle.py (joint BTC+ETH
model; BTC/ETH per-symbol calibration with a p90 stop; SOL transfer mode with
the pooled BTC+ETH calibration), but trained on ALL cached data through the
end of the cache (2026-08). This reads the crypto HOLDOUT window on purpose:
Experiment 49 (retrained walk-forward on that window) PASSED and its
preregistered decision was to refit through the end of the data. The bundle is
marked holdout_read=True and gets its own strategy_id.

Memory: features are kept in float32 (sklearn trees work in float32), random
forests use 6 jobs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant_bot.config import COST_THRESHOLD_PCT  # noqa: E402
from quant_bot.features.build import build_feature_matrix, build_labels  # noqa: E402
from quant_bot.features.pipeline import prune_redundant  # noqa: E402
from quant_bot.forward.signal_engine import FrozenStrategyBundle, FrozenSymbolConfig, save_bundle  # noqa: E402
from quant_bot.signal.model import Tier2RandomForestSignal  # noqa: E402
from scripts.fast_trades import build_trades_with_mae_mfe_fast  # noqa: E402
from scripts.multi_crypto_walkforward import _load_full_cached  # noqa: E402

THRESHOLD, HORIZON = 0.70, 10
SAFETY_MARGIN, STOP_OUT_FRACTION, MAX_LEVERAGE = 0.75, 0.5, 30.0
STRATEGY_ID = "A-CRYPTO-JUPITER-REFIT-20261005"
OUT = ROOT / "docs" / "forward_paper" / "crypto_jupiter_refit_20261005.pkl"


def calibrate(model, frames, feats, stop_percentile):
    probs = [model.predict_proba(f) for f in feats]
    sel = pd.concat([f.loc[p > THRESHOLD] for f, p in zip(feats, probs)], ignore_index=True)
    range_cut, vol_cut = float(sel["range_pos_60"].median()), float(sel["realized_vol_30"].median())
    trades = []
    for frame, f, p in zip(frames, feats, probs):
        mask = ((p > THRESHOLD) & (f["range_pos_60"] < range_cut) & (f["realized_vol_30"] > vol_cut)).to_numpy()
        trades.extend(build_trades_with_mae_mfe_fast(frame["close"].to_numpy(), mask, f["ema_slope_20"].to_numpy(),
                                                     f["ret_1"].to_numpy(), horizon=HORIZON))
    stop = float(np.percentile(np.abs([t["mae"] for t in trades]), stop_percentile))
    return range_cut, vol_cut, stop, min(SAFETY_MARGIN * STOP_OUT_FRACTION / stop, MAX_LEVERAGE), len(trades)


def main():
    frames = {s: _load_full_cached(s) for s in ("BTCUSDT", "ETHUSDT")}
    feats = {s: build_feature_matrix(f).astype("float32") for s, f in frames.items()}
    X = pd.concat([feats["BTCUSDT"], feats["ETHUSDT"]], ignore_index=True)
    y = pd.concat([build_labels(frames[s]["close"], HORIZON, COST_THRESHOLD_PCT) for s in ("BTCUSDT", "ETHUSDT")],
                  ignore_index=True)
    kept, _ = prune_redundant(X, y, corr_threshold=0.9)
    model = Tier2RandomForestSignal(kept, n_estimators=100)
    model.model.n_jobs = 6
    idx = X.sample(n=min(250_000, len(X)), random_state=42).index
    model.fit(X.loc[idx], y.loc[idx])
    del X, y
    configs, report = {}, {}
    for s in ("BTCUSDT", "ETHUSDT"):
        rc, vc, stop, lev, n = calibrate(model, [frames[s]], [feats[s]], 90)
        configs[s] = FrozenSymbolConfig(s, model, THRESHOLD, rc, vc, stop, lev)
        report[s] = dict(range_cut=rc, vol_cut=vc, stop=stop, calib_trades=n)
    rc, vc, stop, lev, n = calibrate(model, [frames["BTCUSDT"], frames["ETHUSDT"]], [feats["BTCUSDT"], feats["ETHUSDT"]], 90)
    configs["SOLUSDT"] = FrozenSymbolConfig("SOLUSDT", model, THRESHOLD, rc, vc, stop, lev)
    report["SOLUSDT"] = dict(range_cut=rc, vol_cut=vc, stop=stop, calib_trades=n)
    end = min(f.index[-1] for f in frames.values())
    bundle = FrozenStrategyBundle(strategy_id=STRATEGY_ID, created_at=pd.Timestamp.now(tz="UTC").isoformat(),
                                  training_boundary=end.isoformat(), configs=configs, live_enabled=False)
    save_bundle(bundle, OUT)
    manifest = {"strategy_id": STRATEGY_ID, "holdout_read": True, "training_end": end.isoformat(),
                "symbols": list(configs), "features": kept, "calibration": report}
    OUT.with_suffix(".json").write_text(json.dumps(manifest, indent=2, default=float))
    print(json.dumps(manifest, indent=2, default=float))


if __name__ == "__main__":
    main()
