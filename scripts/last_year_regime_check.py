"""Is the last year favourable? Frozen crypto bot on 2025-10 -> 2026-10 (out of sample).

Runs the deployed frozen bundle (paper_trading_bot/docs/forward_paper/
strategy_a_bundle.pkl, trained to 2025-03-28) on Binance USDT-M 1m bars from
data.binance.vision, with the paper runner's trade management: entry at the
signal bar close, stop at entry x (1 - stop distance), trailing stop (peak x
(1 - trailing distance) once the high is trailing_activate above entry),
stop checked on the bar low, exit at close after max_holding_bars, one
position per symbol. Signals require 480 contiguous bars (the live gap
guard). Compares per-month trade count / net return with the 2021-2025
walk-forward baseline ledger, then runs the Propr 2-Step rolling-start check.

CPU: the random forests are limited to 6 jobs (half the cores).
Data cache: data/binance_last_year/ (gitignored). Outputs: docs/last_year_*.csv.
"""
import io
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper_trading_bot"
sys.path.insert(0, str(PAPER))
from quant_bot.features.build import build_feature_matrix  # noqa: E402
from quant_bot.forward.signal_engine import MIN_CONTIGUOUS_BARS, load_bundle  # noqa: E402

CACHE = ROOT / "data" / "binance_last_year"
MONTHS = pd.period_range("2025-09", "2026-09", freq="M")   # Sep 2025 = feature warm-up
DAYS = pd.date_range("2026-10-01", "2026-10-04", freq="D")
START = pd.Timestamp("2025-10-01")
BASELINE = ROOT / "docs" / "multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv"
COST = 0.0014                                                # registered round trip
REQ = ["open", "high", "low", "close", "volume", "taker_buy_volume", "taker_sell_volume"]
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
        "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def fetch(sym: str) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    parts = []
    urls = [f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1m/{sym}-1m-{m}.zip" for m in MONTHS]
    urls += [f"https://data.binance.vision/data/futures/um/daily/klines/{sym}/1m/{sym}-1m-{d.date()}.zip" for d in DAYS]
    for url in urls:
        path = CACHE / url.rsplit("/", 1)[1]
        if not path.exists():
            r = requests.get(url, timeout=60)
            if r.status_code != 200:
                print("  missing", path.name, r.status_code, flush=True)
                continue
            path.write_bytes(r.content)
            time.sleep(0.2)
        with zipfile.ZipFile(path) as z:
            raw = z.read(z.namelist()[0]).decode()
        header = 0 if raw.startswith("open_time") else None
        df = pd.read_csv(io.StringIO(raw), header=header, names=None if header == 0 else COLS)
        df.columns = COLS
        parts.append(df)
    df = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time")
    df.index = pd.to_datetime(df.open_time, unit="ms")
    df["taker_sell_volume"] = df.volume - df.taker_buy_volume
    return df[REQ].astype(float)


def simulate(bars: pd.DataFrame, entries: np.ndarray, cfg) -> list[dict]:
    hi, lo, cl, t = bars.high.values, bars.low.values, bars.close.values, bars.index
    trades, i, n = [], 0, len(bars)
    for e in entries:
        if e < i or e + 1 >= n:
            continue                       # one position per symbol
        entry = cl[e]
        stop, peak = entry * (1 - cfg.stop_distance), entry
        k = e + 1
        while True:
            peak = max(peak, hi[k])
            if peak / entry - 1 >= cfg.trailing_activate:
                stop = max(stop, peak * (1 - cfg.trailing_distance))
            if lo[k] <= stop:
                exit_price, reason = stop, "stop"
                break
            if k - e >= cfg.max_holding_bars or k + 1 >= n:
                exit_price, reason = cl[k], "time"
                break
            k += 1
        trades.append({"entry_time": t[e], "exit_time": t[k], "raw_return": exit_price / entry - 1,
                       "stop_distance": cfg.stop_distance, "exit_reason": reason})
        i = k + 1
    return trades


def simulate_close(bars: pd.DataFrame, entries: np.ndarray, cfg) -> list[dict]:
    """Research convention (multi_crypto_walkforward.process_fold): the stop and
    trailing are evaluated on the 1m CLOSE path, exit at the stop level, else
    the close after max_holding_bars."""
    cl, t = bars.close.values, bars.index
    trades, i, n = [], 0, len(bars)
    for e in entries:
        if e < i or e + 1 >= n:
            continue
        entry = cl[e]
        path = cl[e:min(e + cfg.max_holding_bars + 1, n)] / entry - 1
        peak, active, ret, off = -np.inf, False, None, len(path) - 1
        for j, x in enumerate(path):
            if x <= -cfg.stop_distance:
                ret, off, reason = -cfg.stop_distance, j, "stop"
                break
            peak = max(peak, x)
            active = active or peak >= cfg.trailing_activate
            if active and x <= peak - cfg.trailing_distance:
                ret, off, reason = peak - cfg.trailing_distance, j, "trail"
                break
        if ret is None:
            ret, reason = path[-1], "time"
        trades.append({"entry_time": t[e], "exit_time": t[e + off], "raw_return": ret,
                       "stop_distance": cfg.stop_distance, "exit_reason": reason})
        i = e + off + 1
    return trades


def main() -> None:
    bundle = load_bundle(PAPER / "docs" / "forward_paper" / "strategy_a_bundle.pkl")
    all_trades = []
    for sym, cfg in bundle.configs.items():
        bars = fetch(sym)
        cfg.model.model.n_jobs = 6
        X = build_feature_matrix(bars)
        p = cfg.model.predict_proba(X)
        steps = bars.index.to_series().diff().dt.total_seconds().fillna(60).values
        run = np.zeros(len(bars), dtype=int)  # contiguous-bar run length (live gap guard)
        for j in range(1, len(bars)):
            run[j] = run[j - 1] + 1 if steps[j] == 60 else 0
        sel = ((p > cfg.threshold) & (X.range_pos_60 < cfg.range_pos_cut) & (X.realized_vol_30 > cfg.realized_vol_cut)).fillna(False).to_numpy(copy=True)
        sel &= (run >= MIN_CONTIGUOUS_BARS - 1) & (bars.index >= START)
        trades = (simulate_close if "--close" in sys.argv else simulate)(bars, np.flatnonzero(sel), cfg)
        for tr in trades:
            tr["symbol"] = sym
        all_trades += trades
        print(f"{sym}: bars {len(bars)} signals {int(sel.sum())} trades {len(trades)}", flush=True)
        del X, p
    tr = pd.DataFrame(all_trades).sort_values("entry_time")
    suffix = "_close" if "--close" in sys.argv else ""
    tr.to_csv(ROOT / "docs" / f"last_year_trades{suffix}.csv", index=False)

    base = pd.read_csv(BASELINE, parse_dates=["entry_time"])
    base_months = (base.entry_time.max() - base.entry_time.min()).days / 30.44
    tr["net"] = tr.raw_return - COST
    monthly = tr.groupby(tr.entry_time.dt.to_period("M")).agg(
        trades=("net", "size"), mean_net_pct=("net", lambda x: 100 * x.mean()),
        pf=("net", lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.nan))
    monthly.to_csv(ROOT / "docs" / f"last_year_monthly{suffix}.csv")
    bnet = base.raw_return - COST
    pd.set_option("display.width", 160)
    print(monthly.round(3).to_string())
    print(f"\nLAST YEAR: {len(tr)} trades ({len(tr) / 12.1:.1f}/month), mean net {100 * tr.net.mean():.3f}%, "
          f"PF {tr.net[tr.net > 0].sum() / -tr.net[tr.net < 0].sum():.2f}, win {100 * (tr.net > 0).mean():.0f}%")
    print(f"BASELINE 2021-25: {len(base)} trades ({len(base) / base_months:.1f}/month), mean net {100 * bnet.mean():.3f}%, "
          f"PF {bnet[bnet > 0].sum() / -bnet[bnet < 0].sum():.2f}, win {100 * (bnet > 0).mean():.0f}%")
    print("by symbol:", tr.groupby("symbol").net.agg(['size', lambda x: round(100 * x.mean(), 3)]).to_dict('index'))


if __name__ == "__main__":
    main()
