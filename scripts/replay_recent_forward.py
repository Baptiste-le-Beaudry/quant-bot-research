"""Accelerated, isolated replay of the frozen Crypto and Equity paper bots."""
from __future__ import annotations

import argparse
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper_trading_bot"
sys.path.insert(0, str(PAPER))

from quant_bot.equity_forward import EquityForwardEngine, EquityStore
from quant_bot.forward.data import ReadOnlyMarketDataAdapter
from quant_bot.forward.runner import ForwardPaperRunner
from quant_bot.forward.signal_engine import FrozenStrategyASignalEngine, load_bundle
from quant_bot.forward.store import ForwardStateStore
from quant_bot.forward.types import FinalizedBar, MarketQuote


class ReplayAdapter(ReadOnlyMarketDataAdapter):
    def __init__(self):
        self.bar = None

    def finalized_bars(self, *args, **kwargs):
        return []

    def quote(self, symbol):
        b = self.bar
        half = 0.0001  # 2 bps modeled spread; runner adds its frozen slippage/fees.
        return MarketQuote(symbol, b.close_time, b.close_time, b.processing_timestamp,
                           b.close * (1-half), b.close * (1+half))


def metrics(db, equity_table, trade_table, pnl_col, time_col, profile_col="profile"):
    accounts = pd.read_sql_query(f"SELECT * FROM {equity_table}", db)
    trades = pd.read_sql_query(
        f"SELECT * FROM {trade_table} WHERE {pnl_col} IS NOT NULL", db)
    out = []
    for _, account in accounts.iterrows():
        profile = account[profile_col]
        sub = trades[trades[profile_col] == profile]
        initial = float(account["initial_equity"])
        final = float(account["realized_equity"] if "realized_equity" in account else account["equity"])
        gains = sub.loc[sub[pnl_col] > 0, pnl_col].sum()
        losses = -sub.loc[sub[pnl_col] < 0, pnl_col].sum()
        out.append({"profile": profile, "initial": initial, "final": final,
                    "return_pct": 100*(final/initial-1), "closed_trades": len(sub),
                    "win_rate_pct": 100*(sub[pnl_col] > 0).mean() if len(sub) else None,
                    "profit_factor": float(gains/losses) if losses else None,
                    "pnl": float(sub[pnl_col].sum()) if len(sub) else 0.0})
    return pd.DataFrame(out)


def replay_crypto(source, destination, bundle_path):
    src = sqlite3.connect(source); src.row_factory = sqlite3.Row
    rows = src.execute("SELECT * FROM bars ORDER BY open_time,symbol").fetchall()
    store = ForwardStateStore(destination); adapter = ReplayAdapter()
    runner = ForwardPaperRunner(adapter, FrozenStrategyASignalEngine(load_bundle(bundle_path)), store)
    for r in rows:
        bar = FinalizedBar(r["symbol"], r["interval"], pd.Timestamp(r["open_time"]),
            pd.Timestamp(r["close_time"]), pd.Timestamp(r["exchange_timestamp"]),
            pd.Timestamp(r["receive_timestamp"]), pd.Timestamp(r["processing_timestamp"]),
            r["open"], r["high"], r["low"], r["close"], r["volume"],
            r["taker_buy_volume"], r["taker_sell_volume"])
        adapter.bar = bar
        runner.process_bar(bar, signals_enabled=True)
    result = metrics(store.connection, "accounts", "executions", "paper_pnl", "exit_time")
    dd = pd.read_sql_query("SELECT profile,MIN(drawdown)*100 max_drawdown_pct FROM account_snapshots GROUP BY profile", store.connection)
    store.close(); src.close()
    return result.merge(dd, on="profile", how="left"), rows[0]["open_time"], rows[-1]["open_time"]


def replay_equity(source, destination, bundle_path):
    src = sqlite3.connect(source); src.row_factory = sqlite3.Row
    rows = src.execute("SELECT * FROM bars ORDER BY timestamp,symbol").fetchall()
    with open(bundle_path, "rb") as f: bundle = pickle.load(f)
    store = EquityStore(destination); engine = EquityForwardEngine(store, baseline_bundle=bundle)
    store.db.executemany("INSERT OR IGNORE INTO bars VALUES(?,?,?,?,?,?,?)",
        [(r["symbol"],r["timestamp"],r["open"],r["high"],r["low"],r["close"],r["volume"]) for r in rows])
    grouped = {}
    for r in rows: grouped.setdefault(r["timestamp"], []).append(r["symbol"])
    for stamp, symbols in grouped.items():
        ts = pd.Timestamp(stamp)
        for symbol in symbols:
            h = engine._history(symbol, ts)
            if len(h) >= 500: engine._process_exit(symbol, h.loc[ts], ts)
        for symbol in symbols: engine.process(symbol, ts, process_exits=False, signals_enabled=True)
        engine.snapshot(ts)
    result = metrics(store.db, "accounts", "trades", "pnl", "exit_time")
    dd = pd.read_sql_query("SELECT profile,MIN(drawdown)*100 max_drawdown_pct FROM snapshots GROUP BY profile", store.db)
    store.close(); src.close()
    return result.merge(dd, on="profile", how="left"), rows[0]["timestamp"], rows[-1]["timestamp"]


def main():
    p = argparse.ArgumentParser(); p.add_argument("--out", type=Path, default=ROOT/"outputs"/"recent_replay")
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    for f in (a.out/"crypto.sqlite3", a.out/"equity.sqlite3"):
        if f.exists(): f.unlink()
    crypto, c0, c1 = replay_crypto(PAPER/"state"/"forward_state.sqlite3", a.out/"crypto.sqlite3",
        PAPER/"docs"/"forward_paper"/"strategy_a_bundle.pkl")
    equity, e0, e1 = replay_equity(PAPER/"state"/"equity_forward_state.sqlite3", a.out/"equity.sqlite3",
        ROOT/"docs"/"forward_paper"/"equity_strategy_a_bundle.pkl")
    crypto.to_csv(a.out/"crypto_summary.csv", index=False); equity.to_csv(a.out/"equity_summary.csv", index=False)
    meta={"crypto_period":[c0,c1],"equity_period":[e0,e1],"note":"isolated accelerated replay; 2 bps crypto spread assumption"}
    (a.out/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print("CRYPTO", c0, c1); print(crypto.to_string(index=False))
    print("EQUITY", e0, e1); print(equity.to_string(index=False))

if __name__ == "__main__": main()
