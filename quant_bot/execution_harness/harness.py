"""Trade-level and account-level execution harness (v1).

Typical use::

    from quant_bot.execution_harness import ExitRule, run_trades, summarize, simulate_account
    rule = ExitRule(max_bars=50, trail_activation=0.0063, trail_distance=0.008)
    trades = run_trades(candidates, rule, "jupiter_sol")          # per-trade, % costs
    summarize(trades)                                              # PF, mean net, n
    acct = simulate_account(trades, "jupiter_sol", initial_cad=500, position_fraction=0.33)

``candidates`` columns: ``symbol``, ``signal_time`` (tz-aware UTC, open time of
the signal bar), optional ``side`` (+1/-1, default +1), optional
``stop_distance`` (fraction; overrides ``rule.stop_distance``).
"""
from __future__ import annotations

from typing import Callable, Optional

import warnings

import numpy as np
import pandas as pd

from .costs import USD_PER_CAD, PlatformCosts, get_platform
from .data import load_bars
from .fills import ExitRule, simulate_trade

BarsLoader = Callable[[str], pd.DataFrame]


def _platform(p) -> PlatformCosts:
    return p if isinstance(p, PlatformCosts) else get_platform(p)


def run_trades(candidates: pd.DataFrame, rule: ExitRule, platform="research_0p14",
               bars_loader: Optional[BarsLoader] = None, entry_mode: str = "next_open",
               latency_bars: int = 0, notional_usd: Optional[float] = None,
               keep_paths: bool = True) -> pd.DataFrame:
    """Simulate every candidate. Returns one row per candidate (unsupported or
    unmatched candidates are kept with ``status`` != 'ok' so they are counted).

    Cost columns (fractions):
      cost_rt          proportional round trip (fee + half-spread + slippage, both sides)
      net_ret          gross_ret - cost_rt  (size-independent)
      net_ret_at_size  also impact + 2 fixed fees, for ``notional_usd`` (if given)

    Status values (only 'ok' enters PF/means/account by default, review C5):
      ok, unsupported_symbol, signal_bar_missing, no_entry_bar,
      nan_in_window (NaN OHLC between signal and exit), gap_in_window (timestamps
      not contiguous minutes), end_of_data (data ended before the time exit).
    A candidate ``stop_distance`` column is used only if ``rule.use_candidate_stop``.
    """
    if entry_mode == "signal_close":
        warnings.warn("entry_mode='signal_close' fills at the signal bar's close: NOT executable, "
                      "reconciliation with legacy research only", UserWarning, stacklevel=2)
    plat = _platform(platform)
    loader = bars_loader or load_bars
    cand = candidates.copy()
    if "side" not in cand:
        cand["side"] = 1
    if "stop_distance" not in cand:
        cand["stop_distance"] = np.nan
    cand["signal_time"] = pd.to_datetime(cand["signal_time"], utc=True)
    rows = []
    for sym, g in cand.groupby("symbol", sort=True):
        if not plat.supports(sym):
            for i, r in g.iterrows():
                rows.append({"cand_id": i, "symbol": sym, "signal_time": r.signal_time,
                             "status": "unsupported_symbol"})
            continue
        bars = loader(sym)
        ts = bars.index.tz_convert("UTC").tz_localize(None).to_numpy()  # naive UTC datetime64
        o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
        idx = bars.index.get_indexer(g.signal_time)
        for (i, r), s in zip(g.iterrows(), idx):
            base = {"cand_id": i, "symbol": sym, "signal_time": r.signal_time, "side": int(r.side)}
            if s < 0:
                rows.append({**base, "status": "signal_bar_missing"})
                continue
            sd = None if pd.isna(r.stop_distance) else float(r.stop_distance)
            res = simulate_trade(o, h, l, c, int(s), rule, side=int(r.side), stop_distance=sd,
                                 entry_mode=entry_mode, latency_bars=latency_bars, ts=ts)
            if res is None:
                rows.append({**base, "status": "no_entry_bar"})
                continue
            lo = int(s) if entry_mode == "signal_close" else res["entry_idx"]
            hi = res["exit_idx"]
            if (np.isnan(o[lo:hi + 1]).any() or np.isnan(h[lo:hi + 1]).any() or np.isnan(l[lo:hi + 1]).any()
                    or np.isnan(c[lo:hi + 1]).any()):
                status = "nan_in_window"
            elif res["gap_in_window"]:
                status = "gap_in_window"
            elif res["exit_reason"] == "end_of_data":
                status = "end_of_data"
            else:
                status = "ok"
            row = {**base, "status": status, **res,
                   "entry_time": pd.Timestamp(ts[res["entry_idx"]]).tz_localize("UTC"),
                   "exit_time": pd.Timestamp(ts[res["exit_idx"]]).tz_localize("UTC")}
            if keep_paths:
                a, b = (res["entry_idx"] + (1 if entry_mode == "signal_close" else 0)), res["exit_idx"]
                adverse = l[a:b + 1] if r.side == 1 else h[a:b + 1]
                marks = adverse.astype(float).copy()
                if res["exit_reason"] in ("stop", "trail"):
                    marks[-1] = res["exit_price"]  # resting stop filled before the rest of the bar
                row["mark_times"] = ts[a:b + 1]
                row["mark_prices"] = marks
            rows.append(row)
    out = pd.DataFrame(rows).sort_values(["signal_time", "symbol"]).reset_index(drop=True)
    if "gross_ret" not in out:
        out["gross_ret"] = np.nan
    out.attrs.update({"entry_mode": entry_mode, "latency_bars": latency_bars, "rule": rule,
                      "harness_version": _version()})
    return apply_costs(out, plat, notional_usd)


def apply_costs(trades: pd.DataFrame, platform, notional_usd: Optional[float] = None) -> pd.DataFrame:
    """(Re)price simulated trades under a platform. Fills do not depend on the
    platform, so one simulation can be re-costed for every platform. Rows whose
    symbol the platform does not support get status 'unsupported_symbol'."""
    plat = _platform(platform)
    out = trades.copy()
    out.attrs = dict(trades.attrs)
    unsupported = ~out.symbol.map(plat.supports)
    out.loc[unsupported & (out.status == "ok"), "status"] = "unsupported_symbol"
    ok = out.status == "ok"
    for col in ("cost_rt", "net_ret", "net_ret_at_size"):
        out[col] = np.nan
    side_cost = out.loc[ok, "symbol"].map(lambda s: plat.side_cost_pct(s)).astype(float)
    out.loc[ok, "cost_rt"] = 2 * side_cost
    out.loc[ok, "net_ret"] = out.loc[ok, "gross_ret"] - out.loc[ok, "cost_rt"]
    if notional_usd is not None:
        imp = plat.impact_pct_per_10k_usd.value * notional_usd / 10_000.0
        fixed = 2 * plat.fixed_fee_usd_per_order.value / notional_usd
        below_min = notional_usd < plat.min_order_usd.value
        out.loc[ok, "net_ret_at_size"] = np.nan if below_min else out.loc[ok, "net_ret"] - 2 * imp - fixed
    out.attrs.update({"platform": plat.name, "platform_version": plat.version})
    return out


def _version() -> str:
    from . import VERSION
    return VERSION


def profit_factor(x: pd.Series) -> float:
    x = pd.Series(x).dropna()
    loss = -x[x < 0].sum()
    return float(x[x > 0].sum() / loss) if loss > 0 else float("inf")


def summarize(trades: pd.DataFrame, col: str = "net_ret") -> dict:
    ok = trades[trades.status == "ok"]
    x = ok[col]
    return {"n_candidates": int(len(trades)), "n_trades": int(len(ok)),
            "n_skipped": trades.status.ne("ok").sum().item(),
            "status_counts": trades.status.value_counts().to_dict(),
            "mean_gross_pct": 100 * float(ok.gross_ret.mean()) if len(ok) else np.nan,
            f"mean_{col}_pct": 100 * float(x.mean()) if len(ok) else np.nan,
            "pf": profit_factor(x), "win_rate": float((x > 0).mean()) if len(ok) else np.nan,
            "exit_reasons": ok.exit_reason.value_counts().to_dict() if len(ok) else {},
            "n_gap_windows": int(ok.gap_in_window.sum()) if len(ok) else 0,
            "period": (str(ok.entry_time.min()), str(ok.exit_time.max())) if len(ok) else None}


def simulate_account(trades: pd.DataFrame, platform, initial_cad: float = 500.0,
                     usd_per_cad: float = USD_PER_CAD.value, position_fraction: float = 0.10,
                     max_gross_exposure: float = 1.0, one_position_per_symbol: bool = True,
                     charge_funding_conversion: bool = True, mark_net_of_exit_fees: bool = False,
                     period: Optional[tuple] = None, sizer: Optional[Callable] = None) -> dict:
    """Account-level replay of ``run_trades`` output (needs keep_paths=True).

    Sizing: notional = position_fraction * realized equity at entry (USD).
    A trade is skipped if: notional < platform min order, gross exposure would
    exceed ``max_gross_exposure`` * realized equity, or (optionally) the symbol
    already has an open position. Costs in USD: proportional per side on each
    leg's notional (+ linear impact) + fixed fee per order.

    Equity curve: one value per minute = the WORST equity in that minute, open
    positions marked at the bar low (long) / high (short); a stop-exit bar is
    marked at its fill. Realized PnL is booked from the minute after the exit
    bar. Worst day/week use end-of-period values of that curve (UTC days,
    ISO weeks ending Sunday).

    Funding ramp (v1.1, review C2): ``funding_conversion_pct`` per direction on
    the capital + ``funding_fixed_cad`` deducted at withdrawal. CAGR uses
    ``period`` (start, end) if given, else first entry -> last exit.
    ``mark_net_of_exit_fees``: open positions marked net of the exit fee they
    would pay (default False = v1 behaviour).

    ``sizer`` (v1.2): optional ``sizer(trade_row, equity_usd, open_positions, base_notional)
    -> (notional_usd, tag)`` called AFTER the min-order and symbol-busy checks, at entry time,
    on the current realized equity. ``base_notional`` = ``position_fraction * equity`` (the
    cap). ``open_positions`` = list of dicts (symbol, entry_time, notional) still open at the
    entry. A notional <= 0 skips the trade and counts it in ``skips[tag]``; a positive notional
    is re-checked against the platform min order and the exposure cap. ``tag`` is written to the
    ledger column ``size_tag``. ``sizer=None`` reproduces v1.1 exactly.
    """
    plat = _platform(platform)
    if "mark_prices" not in trades:
        raise ValueError("run_trades(..., keep_paths=True) required")
    conv = plat.funding_conversion_pct.value if charge_funding_conversion else 0.0
    initial_usd = initial_cad * usd_per_cad * (1 - conv)
    ok = trades[trades.status == "ok"].sort_values(["entry_time", "symbol"])
    one_min = pd.Timedelta(minutes=1)
    realized = 0.0
    open_pos: list[dict] = []
    ledger, skips = [], {"below_min_order": 0, "exposure_cap": 0, "symbol_busy": 0}
    for _, t in ok.iterrows():
        still = []
        for p in open_pos:
            if p["book_time"] <= t.entry_time:
                realized += p["pnl_usd"]
            else:
                still.append(p)
        open_pos = still
        eq = initial_usd + realized
        notional = position_fraction * eq
        if notional < plat.min_order_usd.value or notional <= 0:
            skips["below_min_order"] += 1
            continue
        if one_position_per_symbol and any(p["symbol"] == t.symbol for p in open_pos):
            skips["symbol_busy"] += 1
            continue
        size_tag = "fraction"
        if sizer is not None:
            view = [{"symbol": p["symbol"], "entry_time": p["entry_time"], "notional": p["notional"]}
                    for p in open_pos]
            notional, size_tag = sizer(t, eq, view, notional)
            if not notional > 0:
                skips[size_tag] = skips.get(size_tag, 0) + 1
                continue
            if notional < plat.min_order_usd.value:
                skips["below_min_order"] += 1
                continue
        if sum(p["notional"] for p in open_pos) + notional > max_gross_exposure * eq + 1e-9:
            skips["exposure_cap"] += 1
            continue
        c_in = notional * plat.side_cost_pct(t.symbol, notional) + plat.fixed_fee_usd_per_order.value
        exit_notional = notional * (1 + t.gross_ret)
        c_out = exit_notional * plat.side_cost_pct(t.symbol, exit_notional) + plat.fixed_fee_usd_per_order.value
        pnl = notional * t.gross_ret - c_in - c_out
        marks = t.side * (t.mark_prices / t.entry_price - 1.0) * notional - c_in
        if mark_net_of_exit_fees:
            mark_notional = notional * (1 + t.side * (t.mark_prices / t.entry_price - 1.0))
            marks = marks - mark_notional * plat.side_cost_pct(t.symbol, notional) - plat.fixed_fee_usd_per_order.value
        p = {"symbol": t.symbol, "entry_time": t.entry_time, "notional": notional, "pnl_usd": pnl,
             "book_time": t.exit_time + one_min, "mark_times": t.mark_times, "marks": marks}
        open_pos.append(p)
        ledger.append({"cand_id": t.cand_id, "symbol": t.symbol, "entry_time": t.entry_time,
                       "exit_time": t.exit_time, "notional_usd": notional, "cost_usd": c_in + c_out,
                       "pnl_usd": pnl, "ret_on_notional": pnl / notional, "equity_before": eq,
                       "size_tag": size_tag,
                       "_marks": (t.mark_times, marks), "_book": t.exit_time + one_min})
    led = pd.DataFrame(ledger)
    if led.empty:
        return {"platform": plat.name, "n_trades": 0, "skips": skips, "initial_usd": initial_usd}
    # minute equity curve (worst mark per minute)
    unreal = pd.concat([pd.Series(m, index=pd.DatetimeIndex(ts).tz_localize("UTC"))
                        for ts, m in led._marks]).groupby(level=0).sum()
    book = pd.Series(led.pnl_usd.to_numpy(), index=pd.DatetimeIndex(led._book)).groupby(level=0).sum()
    idx = unreal.index.union(book.index)
    realized_cum = book.reindex(idx, fill_value=0.0).cumsum()
    equity = initial_usd + realized_cum + unreal.reindex(idx, fill_value=0.0)
    running_max = np.maximum.accumulate(np.r_[initial_usd, equity.to_numpy()])[1:]
    dd = equity / running_max - 1
    eod = equity.resample("1D").last().ffill()
    day_ret = eod / eod.shift(1).fillna(initial_usd) - 1
    eow = equity.resample("W-SUN").last().ffill()
    week_ret = eow / eow.shift(1).fillna(initial_usd) - 1
    day_min = equity.resample("1D").min()
    prev_eod = eod.shift(1).fillna(initial_usd).reindex(day_min.index)
    worst_intraday = (day_min / prev_eod - 1).min()
    final_usd = initial_usd + led.pnl_usd.sum()
    fixed_cad = plat.funding_fixed_cad.value if charge_funding_conversion else 0.0
    final_cad = max(final_usd / usd_per_cad * (1 - conv) - fixed_cad, 0.0)  # cannot withdraw below zero
    start, end = period if period is not None else (led.entry_time.min(), led.exit_time.max())
    years = (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / (365.25 * 86400)
    with np.errstate(over="ignore"):
        cagr_cad = float(np.float64(max(final_cad, 0) / initial_cad) ** (1 / years) - 1) if years > 0 else np.nan
        cagr_trading = float(np.float64(max(final_usd, 0) / initial_usd) ** (1 / years) - 1) if years > 0 else np.nan
    led = led.drop(columns=["_marks", "_book"])
    return {"platform": plat.name, "n_trades": int(len(led)), "skips": skips,
            "initial_cad": initial_cad, "usd_per_cad": usd_per_cad, "initial_usd_after_funding": initial_usd,
            "final_usd": final_usd, "final_cad_after_withdrawal": final_cad,
            "total_return_trading_pct": 100 * (final_usd / initial_usd - 1),
            "total_return_cad_pct": 100 * (final_cad / initial_cad - 1),
            "years": years, "cagr_cad_pct": 100 * cagr_cad, "cagr_trading_pct": 100 * cagr_trading,
            "funding_fixed_cad": fixed_cad, "funding_conversion_pct_per_direction": 100 * conv,
            "mean_pnl_usd": float(led.pnl_usd.mean()),
            "mean_ret_on_notional_pct": 100 * float(led.ret_on_notional.mean()),
            "pf_usd": profit_factor(led.pnl_usd), "total_cost_usd": float(led.cost_usd.sum()),
            "max_dd_pct": 100 * float(dd.min()), "worst_day_pct": 100 * float(day_ret.min()),
            "worst_day_date": str(day_ret.idxmin().date()),
            "worst_intraday_pct": 100 * float(worst_intraday),
            "worst_week_pct": 100 * float(week_ret.min()),
            "worst_week_end": str(week_ret.idxmin().date()),
            "ledger": led, "equity_minute": equity}
