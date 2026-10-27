from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

import pandas as pd


SCHEMA_VERSION = 3


class ForwardStateStore:
    """SQLite WAL store: durable, transactional, idempotent forward state."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._migrate()

    def close(self):
        self.connection.close()

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    def _migrate(self):
        # executescript manages its own transaction and can issue an implicit
        # COMMIT. Keep the migration transaction inside the script so the
        # outer transaction manager never attempts a second COMMIT.
        self.connection.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bars (
                symbol TEXT NOT NULL, open_time TEXT NOT NULL, close_time TEXT NOT NULL,
                exchange_timestamp TEXT NOT NULL, receive_timestamp TEXT NOT NULL,
                processing_timestamp TEXT NOT NULL, interval TEXT NOT NULL,
                open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
                volume REAL NOT NULL, taker_buy_volume REAL NOT NULL, taker_sell_volume REAL NOT NULL,
                data_quality_flags TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(symbol, open_time)
            );
            CREATE TABLE IF NOT EXISTS data_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL,
                bar_timestamp TEXT, observed_at TEXT NOT NULL, event_type TEXT NOT NULL,
                flags TEXT NOT NULL, detail TEXT
            );
            CREATE TABLE IF NOT EXISTS funding_events (
                symbol TEXT NOT NULL, funding_time TEXT NOT NULL,
                rate REAL NOT NULL, mark_price REAL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY(symbol, funding_time)
            );
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, symbol TEXT NOT NULL,
                side TEXT NOT NULL, bar_timestamp TEXT NOT NULL,
                signal_generated_at TEXT NOT NULL, signal_received_at TEXT NOT NULL,
                probability REAL NOT NULL, payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accounts (
                profile TEXT PRIMARY KEY, realized_equity REAL NOT NULL,
                initial_equity REAL NOT NULL, day TEXT NOT NULL,
                day_start_equity REAL NOT NULL, halted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS positions (
                profile TEXT NOT NULL, symbol TEXT NOT NULL, signal_id TEXT NOT NULL,
                side TEXT NOT NULL, entry_bar_timestamp TEXT NOT NULL,
                entry_time TEXT NOT NULL, expected_entry REAL NOT NULL,
                paper_entry REAL NOT NULL, expected_notional REAL NOT NULL,
                notional REAL NOT NULL, risk_dollar REAL NOT NULL,
                expected_stop REAL NOT NULL, paper_stop REAL NOT NULL,
                expected_peak_price REAL NOT NULL, peak_price REAL NOT NULL,
                bars_held INTEGER NOT NULL,
                max_holding_bars INTEGER NOT NULL, trailing_activate REAL NOT NULL,
                trailing_distance REAL NOT NULL, accrued_funding REAL NOT NULL DEFAULT 0,
                PRIMARY KEY(profile, symbol),
                UNIQUE(profile, signal_id)
            );
            CREATE TABLE IF NOT EXISTS expected_positions (
                profile TEXT NOT NULL, symbol TEXT NOT NULL, signal_id TEXT NOT NULL,
                side TEXT NOT NULL, entry_bar_timestamp TEXT NOT NULL,
                expected_entry REAL NOT NULL, expected_notional REAL NOT NULL,
                expected_stop REAL NOT NULL, expected_peak_price REAL NOT NULL,
                bars_held INTEGER NOT NULL, max_holding_bars INTEGER NOT NULL,
                trailing_activate REAL NOT NULL, trailing_distance REAL NOT NULL,
                PRIMARY KEY(profile, symbol), UNIQUE(profile, signal_id)
            );
            CREATE TABLE IF NOT EXISTS signal_decisions (
                profile TEXT NOT NULL, signal_id TEXT NOT NULL, status TEXT NOT NULL,
                reason TEXT, data_quality_flags TEXT NOT NULL DEFAULT '',
                decided_at TEXT NOT NULL,
                PRIMARY KEY(profile, signal_id)
            );
            CREATE TABLE IF NOT EXISTS executions (
                profile TEXT NOT NULL, signal_id TEXT NOT NULL, strategy_id TEXT NOT NULL,
                symbol TEXT NOT NULL, side TEXT NOT NULL, risk_classification TEXT NOT NULL,
                bar_timestamp TEXT NOT NULL, signal_generated_at TEXT NOT NULL,
                signal_received_at TEXT NOT NULL, entry_time TEXT,
                exit_time TEXT, expected_entry_backtest REAL,
                market_bid_at_signal REAL, market_ask_at_signal REAL, mid_price REAL,
                paper_fill_price REAL, expected_notional REAL, paper_notional REAL,
                expected_stop REAL, paper_stop REAL, spread_bps REAL, slippage_bps REAL,
                signal_latency_ms REAL, processing_latency_ms REAL,
                simulated_order_latency_ms REAL, fees REAL, funding REAL,
                expected_exit REAL, paper_exit REAL, expected_pnl REAL, paper_pnl REAL,
                execution_drag REAL, edge_retention REAL, exit_reason TEXT,
                expected_exit_reason TEXT,
                rejected_signal_reason TEXT, data_quality_flags TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(profile, signal_id)
            );
            CREATE TABLE IF NOT EXISTS account_snapshots (
                profile TEXT NOT NULL, timestamp TEXT NOT NULL,
                realized_equity REAL NOT NULL, mtm_equity REAL NOT NULL,
                gross_exposure REAL NOT NULL, net_exposure REAL NOT NULL,
                open_risk REAL NOT NULL, available_margin REAL NOT NULL,
                open_positions INTEGER NOT NULL, losing_positions INTEGER NOT NULL,
                drawdown REAL NOT NULL, PRIMARY KEY(profile, timestamp)
            );
            COMMIT;
            """)
        self.connection.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_version',?)",
            (str(SCHEMA_VERSION),),
        )
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(executions)")}
        if "expected_exit_reason" not in columns:
            self.connection.execute("ALTER TABLE executions ADD COLUMN expected_exit_reason TEXT")

    @staticmethod
    def now() -> str:
        return pd.Timestamp.now(tz="UTC").isoformat()

    def initialize_accounts(self, profiles, initial_equity: float = 100_000.0):
        now = self.now()
        day = pd.Timestamp(now).date().isoformat()
        with self.transaction() as db:
            for profile in profiles:
                db.execute("""INSERT OR IGNORE INTO accounts
                    (profile,realized_equity,initial_equity,day,day_start_equity,halted,updated_at)
                    VALUES(?,?,?,?,?,0,?)""",
                    (profile, initial_equity, initial_equity, day, initial_equity, now))

    def record_bar(self, bar, flags=()) -> bool:
        values = (
            bar.symbol, bar.open_time.isoformat(), bar.close_time.isoformat(),
            bar.exchange_timestamp.isoformat(), bar.receive_timestamp.isoformat(),
            bar.processing_timestamp.isoformat(), bar.interval, bar.open, bar.high,
            bar.low, bar.close, bar.volume, bar.taker_buy_volume,
            bar.taker_sell_volume, ",".join(flags),
        )
        with self.transaction() as db:
            cursor = db.execute("""INSERT OR IGNORE INTO bars VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            return cursor.rowcount == 1

    def record_data_event(self, symbol, bar_timestamp, event_type, flags, detail=""):
        with self.transaction() as db:
            db.execute("""INSERT INTO data_events
                (symbol,bar_timestamp,observed_at,event_type,flags,detail)
                VALUES(?,?,?,?,?,?)""", (symbol, str(bar_timestamp), self.now(), event_type,
                                         ",".join(flags), detail))

    def append_signal(self, signal) -> bool:
        payload = signal.payload()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        import hashlib
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.transaction() as db:
            existing = db.execute("SELECT payload_hash FROM signals WHERE signal_id=?",
                                  (signal.signal_id,)).fetchone()
            if existing:
                if existing["payload_hash"] != digest:
                    raise RuntimeError("immutable signal identity collision")
                return False
            db.execute("""INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?,?)""", (
                signal.signal_id, signal.strategy_id, signal.symbol, signal.side,
                signal.bar_timestamp.isoformat(), signal.signal_generated_at.isoformat(),
                signal.signal_received_at.isoformat(), signal.probability, encoded, digest,
            ))
            return True

    def account(self, profile: str) -> dict:
        row = self.connection.execute("SELECT * FROM accounts WHERE profile=?", (profile,)).fetchone()
        if row is None:
            raise KeyError(profile)
        return dict(row)

    def positions(self, profile: str | None = None) -> list[dict]:
        if profile is None:
            rows = self.connection.execute("SELECT * FROM positions ORDER BY profile,symbol").fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM positions WHERE profile=? ORDER BY symbol",
                                           (profile,)).fetchall()
        return [dict(row) for row in rows]

    def recent_bars(self, symbol: str, limit: int = 1000) -> pd.DataFrame:
        rows = self.connection.execute("""SELECT * FROM bars WHERE symbol=?
            ORDER BY open_time DESC LIMIT ?""", (symbol.upper(), limit)).fetchall()
        if not rows:
            return pd.DataFrame()
        frame = pd.DataFrame(map(dict, rows)).sort_values("open_time")
        frame.index = pd.to_datetime(frame.pop("open_time"), utc=True)
        return frame

    def signal_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM signals").fetchone()[0])

    def report_frames(self) -> dict[str, pd.DataFrame]:
        return {
            name: pd.read_sql_query(f"SELECT * FROM {table}", self.connection)
            for name, table in {
                "accounts": "accounts", "positions": "positions",
                "signals": "signals", "decisions": "signal_decisions",
                "executions": "executions", "snapshots": "account_snapshots",
                "data_events": "data_events",
            }.items()
        }
