from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Protocol

import pandas as pd

from quant_bot.config import MAX_DAILY_LOSS_PCT, RISK_PROFILES, SLIPPAGE_PCT_EST, TAKER_FEE_PCT

from .data import DataIntegrityGuard, ReadOnlyMarketDataAdapter
from .store import ForwardStateStore
from .types import FinalizedBar, FundingEvent, MarketQuote, SignalEvent


class ForwardSignalEngine(Protocol):
    strategy_id: str

    def on_finalized_bar(self, bar: FinalizedBar, history: pd.DataFrame) -> SignalEvent | None:
        ...


@dataclass(frozen=True)
class ForwardRuntimeConfig:
    profiles: tuple[str, ...] = ("normal", "aggressive", "max-risk")
    initial_equity: float = 100_000.0
    fee_per_side: float = TAKER_FEE_PCT
    slippage_per_side: float = SLIPPAGE_PCT_EST / 2
    min_equity_fraction: float = 0.25
    max_daily_loss_fraction: float = MAX_DAILY_LOSS_PCT
    quote_max_age_seconds: float = 120.0


class ForwardPaperRunner:
    """Continuous paper engine. It only accepts a read-only market adapter."""

    def __init__(self, adapter: ReadOnlyMarketDataAdapter, signal_engine: ForwardSignalEngine,
                 store: ForwardStateStore, guard: DataIntegrityGuard | None = None,
                 config: ForwardRuntimeConfig = ForwardRuntimeConfig()):
        if not isinstance(adapter, ReadOnlyMarketDataAdapter):
            raise TypeError("forward runner requires ReadOnlyMarketDataAdapter")
        self.adapter, self.signal_engine, self.store = adapter, signal_engine, store
        self.guard, self.config = guard or DataIntegrityGuard(), config
        self.store.initialize_accounts(config.profiles, config.initial_equity)
        self.last_prices: dict[str, float] = {}
        self._restore_guard()

    def _restore_guard(self):
        rows = self.store.connection.execute("""SELECT b.* FROM bars b JOIN
            (SELECT symbol,MAX(open_time) AS latest FROM bars
             WHERE data_quality_flags='' GROUP BY symbol) x
            ON b.symbol=x.symbol AND b.open_time=x.latest""").fetchall()
        for row in rows:
            self.guard.restore(row["symbol"], row["open_time"], row["close"])
            self.last_prices[row["symbol"]] = float(row["close"])

    def process_bar(self, bar: FinalizedBar) -> dict:
        quality = self.guard.check(bar)
        if not quality.accepted:
            self.store.record_data_event(bar.symbol, bar.open_time,
                                         "DATA_GUARD_TRIGGERED", quality.flags)
            return {"status": "DATA_GUARD_TRIGGERED", "flags": quality.flags}
        # Rejected/incomplete observations must never occupy the canonical
        # bar key: the finalized replacement at the same open_time must remain
        # processable. Invalid observations live only in data_events.
        inserted = self.store.record_bar(bar)
        if not inserted:
            self.store.record_data_event(bar.symbol, bar.open_time,
                                         "DATA_GUARD_TRIGGERED", ("DUPLICATE_BAR",))
            return {"status": "DATA_GUARD_TRIGGERED", "flags": ("DUPLICATE_BAR",)}

        self.last_prices[bar.symbol] = bar.close
        self._process_exits(bar)
        history = self.store.recent_bars(bar.symbol, 1000)
        signal = self.signal_engine.on_finalized_bar(bar, history)
        if signal is not None:
            if signal.bar_timestamp != bar.open_time:
                raise ValueError("signal bar timestamp differs from finalized bar")
            if signal.signal_generated_at < bar.close_time:
                raise ValueError("bar-close information used before bar close")
            self.store.append_signal(signal)
            quote = self.adapter.quote(bar.symbol)
            quote_flags = self._quote_flags(quote, bar)
            for profile in self.config.profiles:
                self._process_signal_for_profile(profile, signal, quote, quote_flags)
        self._snapshot_all(bar.processing_timestamp)
        return {"status": "PROCESSED", "signal_id": signal.signal_id if signal else None}

    def process_funding(self, event: FundingEvent) -> bool:
        """Accrue one settled event exactly once to positions crossing its time.

        Binance convention: a positive rate is paid by longs and received by
        shorts. Funding affects only paper PnL; the frictionless expected
        shadow remains the registered backtest expectation.
        """
        with self.store.transaction() as db:
            inserted = db.execute("""INSERT OR IGNORE INTO funding_events
                (symbol,funding_time,rate,mark_price,observed_at)
                VALUES(?,?,?,?,?)""", (
                event.symbol, event.funding_time.isoformat(), event.rate,
                event.mark_price, self.store.now(),
            ))
            if inserted.rowcount != 1:
                return False
            positions = db.execute("""SELECT profile,symbol,side,notional
                FROM positions WHERE symbol=? AND entry_time<=?""",
                (event.symbol, event.funding_time.isoformat())).fetchall()
            for position in positions:
                direction = 1.0 if position["side"] == "LONG" else -1.0
                payment = direction * float(position["notional"]) * event.rate
                db.execute("""UPDATE positions
                    SET accrued_funding=accrued_funding+?
                    WHERE profile=? AND symbol=?""",
                    (payment, position["profile"], position["symbol"]))
            return True

    def _quote_flags(self, quote: MarketQuote, bar: FinalizedBar) -> tuple[str, ...]:
        flags = []
        if quote.bid <= 0 or quote.ask <= 0 or quote.bid > quote.ask:
            flags.append("INVALID_QUOTE")
        if quote.receive_timestamp < bar.close_time:
            flags.append("PRE_CLOSE_QUOTE")
        if (quote.receive_timestamp - quote.exchange_timestamp).total_seconds() > self.config.quote_max_age_seconds:
            flags.append("STALE_QUOTE")
        return tuple(flags)

    def _refresh_day(self, db, account: dict, now: pd.Timestamp) -> dict:
        day = now.date().isoformat()
        if account["day"] != day:
            db.execute("""UPDATE accounts SET day=?,day_start_equity=realized_equity,
                halted=0,updated_at=? WHERE profile=?""",
                (day, now.isoformat(), account["profile"]))
            account.update(day=day, day_start_equity=account["realized_equity"], halted=0)
        return account

    def _process_signal_for_profile(self, profile: str, signal: SignalEvent,
                                    quote: MarketQuote, quote_flags: tuple[str, ...]):
        now = quote.processing_timestamp
        with self.store.transaction() as db:
            if db.execute("SELECT 1 FROM signal_decisions WHERE profile=? AND signal_id=?",
                          (profile, signal.signal_id)).fetchone():
                return
            account = dict(db.execute("SELECT * FROM accounts WHERE profile=?", (profile,)).fetchone())
            account = self._refresh_day(db, account, now)
            positions = [dict(row) for row in db.execute(
                "SELECT * FROM positions WHERE profile=?", (profile,)).fetchall()]
            reason = None
            if quote_flags:
                reason = "DATA_GUARD_TRIGGERED"
            elif account["halted"]:
                reason = "ACCOUNT_HALTED"
            elif account["realized_equity"] <= account["initial_equity"] * self.config.min_equity_fraction:
                reason = "KILL_SWITCH_MIN_EQUITY"
            elif account["realized_equity"] <= account["day_start_equity"] * (1 - self.config.max_daily_loss_fraction):
                reason = "KILL_SWITCH_DAILY_LOSS"
                db.execute("UPDATE accounts SET halted=1,updated_at=? WHERE profile=?",
                           (now.isoformat(), profile))
            elif any(position["symbol"] == signal.symbol for position in positions):
                reason = "POSITION_ALREADY_OPEN"

            limits = RISK_PROFILES[profile]
            equity = float(account["realized_equity"])
            open_risk = sum(float(position["risk_dollar"]) for position in positions)
            gross = sum(float(position["notional"]) for position in positions)
            desired_risk = equity * limits["risk_pct"]
            desired_risk = min(desired_risk,
                               max(0.0, equity * limits["max_portfolio_open_risk"] - open_risk))
            leverage = min(desired_risk / (equity * signal.stop_distance),
                           signal.leverage_safe, limits["hard_leverage_ceiling"])
            leverage = min(leverage, max(0.0, equity * limits["max_gross_exposure"] - gross) / equity)
            if not reason and leverage <= 0:
                reason = "PORTFOLIO_CAP"

            risk_classification = "EXTREME_RISK|LIVE_DISABLED|NOT_RECOMMENDED_FOR_CAPITAL" if profile == "max-risk" else "PAPER_ONLY|LIVE_DISABLED"
            signal_latency = (signal.signal_received_at - signal.bar_timestamp).total_seconds() * 1000
            processing_latency = (now - signal.signal_received_at).total_seconds() * 1000
            base_execution = (
                profile, signal.signal_id, signal.strategy_id, signal.symbol, signal.side,
                risk_classification, signal.bar_timestamp.isoformat(),
                signal.signal_generated_at.isoformat(), signal.signal_received_at.isoformat(),
            )
            if reason:
                db.execute("""INSERT INTO signal_decisions VALUES(?,?,?,?,?,?)""",
                           (profile, signal.signal_id, "REJECTED", reason,
                            ",".join(quote_flags), now.isoformat()))
                db.execute("""INSERT INTO executions
                    (profile,signal_id,strategy_id,symbol,side,risk_classification,
                     bar_timestamp,signal_generated_at,signal_received_at,
                     signal_latency_ms,processing_latency_ms,rejected_signal_reason,data_quality_flags)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (*base_execution, signal_latency, processing_latency, reason, ",".join(quote_flags)))
                return

            expected_notional = equity * leverage
            paper_entry = quote.ask * (1 + self.config.slippage_per_side) if signal.side == "LONG" else quote.bid * (1 - self.config.slippage_per_side)
            expected_stop = signal.expected_entry_backtest * (1 - signal.stop_distance if signal.side == "LONG" else 1 + signal.stop_distance)
            paper_stop = paper_entry * (1 - signal.stop_distance if signal.side == "LONG" else 1 + signal.stop_distance)
            risk_dollar = expected_notional * signal.stop_distance
            entry_fee = expected_notional * self.config.fee_per_side
            new_equity = equity - entry_fee
            db.execute("""UPDATE accounts SET realized_equity=?,updated_at=? WHERE profile=?""",
                       (new_equity, now.isoformat(), profile))
            db.execute("""INSERT INTO positions VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                profile, signal.symbol, signal.signal_id, signal.side,
                signal.bar_timestamp.isoformat(), now.isoformat(),
                signal.expected_entry_backtest, paper_entry, expected_notional,
                expected_notional, risk_dollar, expected_stop, paper_stop,
                signal.expected_entry_backtest, paper_entry, 0,
                signal.max_holding_bars, signal.trailing_activate,
                signal.trailing_distance, 0.0,
            ))
            db.execute("""INSERT INTO expected_positions VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                profile, signal.symbol, signal.signal_id, signal.side,
                signal.bar_timestamp.isoformat(), signal.expected_entry_backtest,
                expected_notional, expected_stop, signal.expected_entry_backtest,
                0, signal.max_holding_bars, signal.trailing_activate,
                signal.trailing_distance,
            ))
            db.execute("INSERT INTO signal_decisions VALUES(?,?,?,?,?,?)",
                       (profile, signal.signal_id, "OPENED", None, "", now.isoformat()))
            slippage_bps = abs(paper_entry / quote.ask - 1) * 10_000 if signal.side == "LONG" else abs(paper_entry / quote.bid - 1) * 10_000
            db.execute("""INSERT INTO executions
                (profile,signal_id,strategy_id,symbol,side,risk_classification,
                 bar_timestamp,signal_generated_at,signal_received_at,entry_time,
                 expected_entry_backtest,market_bid_at_signal,market_ask_at_signal,
                 mid_price,paper_fill_price,expected_notional,paper_notional,
                 expected_stop,paper_stop,spread_bps,slippage_bps,signal_latency_ms,
                 processing_latency_ms,simulated_order_latency_ms,fees,funding,
                 data_quality_flags)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*base_execution, now.isoformat(), signal.expected_entry_backtest,
                 quote.bid, quote.ask, quote.mid, paper_entry, expected_notional,
                 expected_notional, expected_stop, paper_stop, quote.spread_bps,
                 slippage_bps, signal_latency, processing_latency, 0.0, entry_fee,
                 0.0, ""))

    def _process_exits(self, bar: FinalizedBar):
        for profile in self.config.profiles:
            expected = self.store.connection.execute(
                "SELECT * FROM expected_positions WHERE profile=? AND symbol=?",
                (profile, bar.symbol)).fetchone()
            if expected is not None and pd.Timestamp(expected["entry_bar_timestamp"]) < bar.open_time:
                self._update_or_close_expected(profile, dict(expected), bar)
            position = self.store.connection.execute(
                "SELECT * FROM positions WHERE profile=? AND symbol=?",
                (profile, bar.symbol)).fetchone()
            if position is None or pd.Timestamp(position["entry_bar_timestamp"]) >= bar.open_time:
                continue
            self._update_or_close(profile, dict(position), bar)

    def _update_or_close(self, profile: str, position: dict, bar: FinalizedBar):
        long = position["side"] == "LONG"
        bars_held = int(position["bars_held"]) + 1
        paper_peak = max(position["peak_price"], bar.high) if long else min(position["peak_price"], bar.low)
        paper_stop = position["paper_stop"]
        if long and paper_peak / position["paper_entry"] - 1 >= position["trailing_activate"]:
            paper_stop = max(paper_stop, paper_peak * (1 - position["trailing_distance"]))
        if not long and position["paper_entry"] / paper_peak - 1 >= position["trailing_activate"]:
            paper_stop = min(paper_stop, paper_peak * (1 + position["trailing_distance"]))

        stop_hit = bar.low <= paper_stop if long else bar.high >= paper_stop
        time_exit = bars_held >= int(position["max_holding_bars"])
        if not stop_hit and not time_exit:
            with self.store.transaction() as db:
                db.execute("""UPDATE positions SET expected_stop=?,paper_stop=?,
                    expected_peak_price=?,peak_price=?,bars_held=?
                    WHERE profile=? AND symbol=?""",
                    (position["expected_stop"], paper_stop, position["expected_peak_price"], paper_peak, bars_held,
                     profile, position["symbol"]))
            return

        reason = "stop" if stop_hit else "time"
        if stop_hit:
            paper_exit = paper_stop * (1 - self.config.slippage_per_side if long else 1 + self.config.slippage_per_side)
        else:
            paper_exit = bar.close * (1 - self.config.slippage_per_side if long else 1 + self.config.slippage_per_side)
        direction = 1 if long else -1
        gross_pnl = direction * (paper_exit / position["paper_entry"] - 1) * position["notional"]
        exit_fee = position["notional"] * self.config.fee_per_side
        entry_fee = position["notional"] * self.config.fee_per_side
        funding = float(position["accrued_funding"])
        paper_pnl = gross_pnl - entry_fee - exit_fee - funding
        now = bar.processing_timestamp.isoformat()
        with self.store.transaction() as db:
            account = dict(db.execute("SELECT * FROM accounts WHERE profile=?", (profile,)).fetchone())
            # Entry fee was already realized at open; add gross less exit fee/funding.
            new_equity = account["realized_equity"] + gross_pnl - exit_fee - funding
            db.execute("UPDATE accounts SET realized_equity=?,updated_at=? WHERE profile=?",
                       (new_equity, now, profile))
            db.execute("DELETE FROM positions WHERE profile=? AND symbol=?", (profile, position["symbol"]))
            db.execute("""UPDATE executions SET exit_time=?,fees=?,funding=?,
                paper_exit=?,paper_pnl=?,exit_reason=?,paper_stop=?
                WHERE profile=? AND signal_id=?""",
                (now, entry_fee + exit_fee, funding, paper_exit, paper_pnl, reason,
                 paper_stop,
                 profile, position["signal_id"]))
            self._finalize_comparison(db, profile, position["signal_id"])

    def _update_or_close_expected(self, profile: str, position: dict, bar: FinalizedBar):
        long = position["side"] == "LONG"
        held = int(position["bars_held"]) + 1
        peak = (max(position["expected_peak_price"], bar.high) if long
                else min(position["expected_peak_price"], bar.low))
        stop = float(position["expected_stop"])
        if long and peak / position["expected_entry"] - 1 >= position["trailing_activate"]:
            stop = max(stop, peak * (1 - position["trailing_distance"]))
        if not long and position["expected_entry"] / peak - 1 >= position["trailing_activate"]:
            stop = min(stop, peak * (1 + position["trailing_distance"]))
        stop_hit = bar.low <= stop if long else bar.high >= stop
        time_exit = held >= int(position["max_holding_bars"])
        if not stop_hit and not time_exit:
            with self.store.transaction() as db:
                db.execute("""UPDATE expected_positions SET expected_stop=?,
                    expected_peak_price=?,bars_held=? WHERE profile=? AND symbol=?""",
                    (stop, peak, held, profile, position["symbol"]))
            return
        expected_exit = stop if stop_hit else bar.close
        direction = 1 if long else -1
        gross = direction * (expected_exit / position["expected_entry"] - 1) * position["expected_notional"]
        pnl = gross - 2 * position["expected_notional"] * self.config.fee_per_side
        reason = "stop" if stop_hit else "time"
        with self.store.transaction() as db:
            db.execute("DELETE FROM expected_positions WHERE profile=? AND symbol=?",
                       (profile, position["symbol"]))
            db.execute("""UPDATE executions SET expected_exit=?,expected_pnl=?,
                expected_stop=?, expected_exit_reason=? WHERE profile=? AND signal_id=?""",
                (expected_exit, pnl, stop, reason, profile, position["signal_id"]))
            self._finalize_comparison(db, profile, position["signal_id"])

    @staticmethod
    def _finalize_comparison(db, profile: str, signal_id: str):
        row = db.execute("SELECT expected_pnl,paper_pnl FROM executions WHERE profile=? AND signal_id=?",
                         (profile, signal_id)).fetchone()
        if row is None or row["expected_pnl"] is None or row["paper_pnl"] is None:
            return
        expected, paper = float(row["expected_pnl"]), float(row["paper_pnl"])
        db.execute("""UPDATE executions SET execution_drag=?,edge_retention=?
            WHERE profile=? AND signal_id=?""",
            (paper - expected, paper / expected if expected else None, profile, signal_id))

    def _snapshot_all(self, timestamp: pd.Timestamp):
        for profile in self.config.profiles:
            account = self.store.account(profile)
            positions = self.store.positions(profile)
            unrealized, gross, net, open_risk, losing = 0.0, 0.0, 0.0, 0.0, 0
            for position in positions:
                price = self.last_prices.get(position["symbol"], position["paper_entry"])
                direction = 1 if position["side"] == "LONG" else -1
                pnl = direction * (price / position["paper_entry"] - 1) * position["notional"]
                unrealized += pnl
                gross += position["notional"]
                net += direction * position["notional"]
                open_risk += position["risk_dollar"]
                losing += int(pnl < 0)
            realized = account["realized_equity"]
            mtm = realized + unrealized
            initial = account["initial_equity"]
            peak_row = self.store.connection.execute(
                "SELECT MAX(mtm_equity) FROM account_snapshots WHERE profile=?", (profile,)).fetchone()
            peak = max(initial, float(peak_row[0] or initial), mtm)
            drawdown = mtm / peak - 1
            available = mtm - gross / RISK_PROFILES[profile]["hard_leverage_ceiling"]
            with self.store.transaction() as db:
                db.execute("""INSERT OR REPLACE INTO account_snapshots VALUES
                    (?,?,?,?,?,?,?,?,?,?,?)""", (
                    profile, timestamp.isoformat(), realized, mtm,
                    gross / mtm if mtm else math.inf, net / mtm if mtm else math.inf,
                    open_risk / mtm if mtm else math.inf, available,
                    len(positions), losing, drawdown,
                ))
