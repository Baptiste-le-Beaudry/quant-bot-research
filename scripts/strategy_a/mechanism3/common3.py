"""scripts/strategy_a/mechanism3/common3.py -- shared helpers for the
Transfer Validation mandate (docs/strategy_a/STRATEGY_A_TRANSFER_VALIDATION.md).
Read-only reuse of frozen Strategy A machinery, same discipline as
mechanism2/common.py. Nothing in quant_bot/ or scripts/multi_crypto_walkforward.py
is modified.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, REPO_ROOT)

import numpy as np
import pandas as pd

from quant_bot.features.build import build_feature_matrix

MECH3_DOCS = os.path.join(REPO_ROOT, "docs", "strategy_a", "mechanism3")
os.makedirs(MECH3_DOCS, exist_ok=True)
FEATS_CACHE_DIR = os.path.join(REPO_ROOT, "docs", "_full_data_cache")

SYMBOLS_9 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
             "ADAUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT"]
NEW_ASSETS = ["TSLA", "NVDA", "MSTR", "TQQQ", "SOXL", "SPXL"]
ASSET_TYPE = {"TSLA": "high-vol liquid stock", "NVDA": "high-vol liquid stock",
              "MSTR": "high-vol liquid stock", "TQQQ": "3x leveraged ETF",
              "SOXL": "3x leveraged ETF", "SPXL": "3x leveraged ETF"}

TRADES_CSV = os.path.join(REPO_ROOT, "docs", "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv")


def load_equity_1m(symbol: str) -> pd.DataFrame:
    import glob
    pattern = os.path.join(REPO_ROOT, "data", f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def load_crypto_full_feats(symbol: str) -> pd.DataFrame:
    """Reuse mechanism2's already-cached full-history feature parquet."""
    path = os.path.join(FEATS_CACHE_DIR, f"{symbol}_full_feats.parquet")
    return pd.read_parquet(path)


def crypto_generic_pooled(feature: str) -> pd.Series:
    parts = []
    for sym in SYMBOLS_9:
        feats = load_crypto_full_feats(sym)
        if feature in feats.columns:
            parts.append(feats[feature].dropna())
    return pd.concat(parts) if parts else pd.Series(dtype=float)


_TRADES_CACHE = None


def crypto_selected_feats() -> pd.DataFrame:
    """Feature values at each of the 9 symbols' REAL Strategy-A entry_times
    (frozen trade log, read-only). Pooled across all 9 symbols -- a more
    representative 'crypto selected' reference population than the prior
    mechanism report's BTC/ETH-only comparison (disclosed difference)."""
    global _TRADES_CACHE
    if _TRADES_CACHE is not None:
        return _TRADES_CACHE
    trades = pd.read_csv(TRADES_CSV, parse_dates=["entry_time"])
    rows = []
    for sym in SYMBOLS_9:
        sym_times = trades.loc[trades["symbol"] == sym, "entry_time"]
        if not len(sym_times):
            continue
        feats = load_crypto_full_feats(sym)
        sub = feats.reindex(sym_times).dropna(how="all")
        sub["symbol"] = sym
        rows.append(sub)
    _TRADES_CACHE = pd.concat(rows) if rows else pd.DataFrame()
    return _TRADES_CACHE


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
