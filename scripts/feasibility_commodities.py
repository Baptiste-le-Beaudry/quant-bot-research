"""Feasibility probe (no strategy, no model): can Strategy A's dip-buy edge
plausibly transfer to gold / silver / oil?

The transferability study found the blocker for QQQ/SPY was the volatility
regime (realized_vol_30 / atr_norm far below crypto's, the features that
drive the edge) and cost relative to the typical move. This pulls a recent
sample of Dukascopy 1m BID+ASK candles and compares, per instrument:
- realized_vol_30 and atr_norm distributions vs BTC/SOL (same feature code);
- the real BID/ASK spread, and spread / ATR (cost as a share of a 1m move)
  vs crypto's registered 0.14 % round trip / ATR.
Outputs: outputs/commodities_feasibility/. Single process, paced requests.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "paper_trading_bot"))
from quant_bot.equity_forward import decode_dukascopy_candles  # noqa: E402
from quant_bot.features.build import build_feature_matrix  # noqa: E402

OUT = ROOT / "outputs" / "commodities_feasibility"
CODES = {"XAUUSD": "XAU-USD", "XAGUSD": "XAG-USD", "WTI": "LIGHT.CMD-USD", "BRENT": "BRENT.CMD-USD"}
DAYS = 30
HEADERS = {"User-Agent": "Mozilla/5.0"}
CRYPTO_CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else None  # optional Binance bars pickle


def fetch(code: str, side: str, day: pd.Timestamp, session: requests.Session) -> pd.DataFrame:
    url = f"https://jetta.dukascopy.com/v1/candles/minute/{code}/{side}/{day.year}/{day.month}/{day.day}"
    data = session.get(url, headers=HEADERS, timeout=20).json()
    return decode_dukascopy_candles(data) if data.get("times") else pd.DataFrame()


def features(df: pd.DataFrame) -> pd.DataFrame:
    h = df[["open", "high", "low", "close", "volume"]].copy()
    h["taker_buy_volume"] = h.volume / 2
    h["taker_sell_volume"] = h.volume / 2
    return build_feature_matrix(h)[["realized_vol_30", "atr_norm"]]


def summarize(name: str, X: pd.DataFrame, spread_pct: float | None) -> dict:
    q = X.quantile([0.5, 0.9]).to_dict()
    atr = X.atr_norm.median()
    return {"instrument": name, "bars": int(len(X)),
            "rv30_median": q["realized_vol_30"][0.5], "rv30_p90": q["realized_vol_30"][0.9],
            "atr_norm_median_pct": 100 * atr, "atr_norm_p90_pct": 100 * q["atr_norm"][0.9],
            "spread_median_pct": spread_pct,
            "round_trip_cost_over_atr": (spread_pct / 100) / atr if spread_pct is not None else None}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    days = [d for d in pd.bdate_range(end=pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=1), periods=DAYS)]
    rows = []
    for name, code in CODES.items():
        bid, ask = [], []
        for d in days:
            for side, sink in (("BID", bid), ("ASK", ask)):
                try:
                    sink.append(fetch(code, side, d, session))
                except Exception as exc:
                    print(name, side, d.date(), "failed:", exc, flush=True)
                time.sleep(0.4)
        b = pd.concat([x for x in bid if len(x)]).sort_index()
        a = pd.concat([x for x in ask if len(x)]).sort_index()
        b = b[~b.index.duplicated()]
        a = a[~a.index.duplicated()]
        both = b.join(a[["close"]].rename(columns={"close": "ask_close"}), how="inner")
        both = both[both.volume > 0]  # flat-filled gap bars carry no trading
        spread = 100 * ((both.ask_close - both.close) / both.close).median()
        rows.append(summarize(name, features(b[b.volume > 0]), float(spread)))
        print(rows[-1], flush=True)
    if CRYPTO_CACHE and CRYPTO_CACHE.exists():
        bars = pd.read_pickle(CRYPTO_CACHE)
        for sym in ("BTCUSDT", "SOLUSDT", "XRPUSDT"):
            g = bars[bars.symbol == sym].copy()
            g.index = pd.to_datetime(g.open_ms, unit="ms", utc=True)
            # registered crypto cost: 0.14 % round trip (perp taker fees + slippage)
            rows.append(summarize(sym, features(g.sort_index()), 0.14))
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "volatility_cost_comparison.csv", index=False)
    (OUT / "meta.json").write_text(json.dumps({"days": [str(d.date()) for d in days], "codes": CODES}, indent=2))
    pd.set_option("display.width", 200)
    print(res.round(5).to_string(index=False))


if __name__ == "__main__":
    main()
