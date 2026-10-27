"""
scripts/phase3_baseline.py — Phase 3: does the data contain ANY edge before
we build features/models around it (SPEC.md section 1, section 13a decision
2 for the horizon experiment)?

Three no-AI rule families from the plan (A: momentum breakout, B: mean
reversion, C: trend-following pullback), each tested against costs, a
buy-and-hold reference, and a random-entry null baseline of the same trade
count — across all four candidate label horizons (5/10/15/30min), so the
horizon decision (SPEC.md section 6) is made from evidence, not assumption.
Also includes a cheap DSP diagnostic (rolling return autocorrelation +
one-shot FFT dominant-period check) per the plan's "E. Cycles/FFT — verify
statistically, don't assume predictive" instruction.

Runs on the TRAIN slice only (first 60% chronologically, SPEC.md section 8)
— this is exploration, not the number that decides anything final.

Usage:
    python scripts/phase3_baseline.py --symbol BTCUSDT
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import glob
import numpy as np
import pandas as pd

from quant_bot.config import (
    DATA_DIR, LABEL_HORIZON_CANDIDATES, TRAIN_FRACTION, VALIDATION_FRACTION,
    ROUND_TRIP_FEE_PCT, SLIPPAGE_PCT_EST,
)
from quant_bot.backtest.simple_engine import evaluate_signal, buy_and_hold_return_pct, null_baseline

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ── Data loading ─────────────────────────────────────────────────────────

def _load_full(symbol: str) -> pd.DataFrame:
    pattern = os.path.join(DATA_DIR, f"{symbol}_1m_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No klines CSV for {symbol} in {DATA_DIR} — run scripts/download_data.py first")
    df = pd.read_csv(files[-1], index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def load_split(symbol: str, split: str, verbose: bool = True) -> pd.DataFrame:
    """split: 'train' (first TRAIN_FRACTION), 'validation' (next
    VALIDATION_FRACTION), or 'holdout' (the rest — SPEC.md section 8: touch
    this once, after everything else is frozen, never for iteration)."""
    df = _load_full(symbol)
    n = len(df)
    train_end = int(n * TRAIN_FRACTION)
    val_end = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))
    bounds = {
        "train": (0, train_end), "validation": (train_end, val_end), "holdout": (val_end, n),
        "oos": (train_end, n),  # VALIDATION+HOLDOUT combined: everything not used to fit the
                                  # model -- for generalization checks on data/configs that were
                                  # never tuned using this symbol at all (see diagnostic scripts)
    }
    if split not in bounds:
        raise ValueError(f"split must be one of {list(bounds)}, got {split!r}")
    start, end = bounds[split]
    out = df.iloc[start:end]
    if verbose:
        print(f"{symbol} [{split.upper()}]: {len(out):,} bars "
              f"({out.index[0]:%Y-%m-%d} -> {out.index[-1]:%Y-%m-%d})")
    return out


def load_train_slice(symbol: str) -> pd.DataFrame:
    return load_split(symbol, "train")


# ── Feature helpers (throwaway/exploratory — the real, pruned feature set
#    per SPEC.md section 5 gets built in quant_bot.features after this
#    script justifies that it's worth building) ─────────────────────────

def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum()


def rising_edge(cond: pd.Series) -> pd.Series:
    """Only the first bar of a new True run — avoids counting the same
    setup dozens of times while a condition stays true."""
    return cond & ~cond.shift(1).fillna(False)


# ── Rule family A: momentum breakout + volume + trend ───────────────────

def signal_momentum_breakout(df: pd.DataFrame, n: int = 30, vol_mult: float = 1.5) -> pd.Series:
    prior_high = df["high"].shift(1).rolling(n).max()
    prior_low = df["low"].shift(1).rolling(n).min()
    vol_confirm = df["volume"] > df["volume"].rolling(n).mean() * vol_mult
    trend_up = df["close"] > ema(df["close"], 50)
    trend_down = df["close"] < ema(df["close"], 50)

    long_cond = rising_edge((df["close"] > prior_high) & vol_confirm & trend_up)
    short_cond = rising_edge((df["close"] < prior_low) & vol_confirm & trend_down)

    signal = pd.Series(0, index=df.index)
    signal[long_cond] = 1
    signal[short_cond] = -1
    return signal


# ── Rule family B: mean reversion to VWAP + confirmation candle ─────────

def signal_mean_reversion(df: pd.DataFrame, window: int = 60, z_thresh: float = 2.0) -> pd.Series:
    vwap = rolling_vwap(df, window)
    dist = df["close"] - vwap
    z = dist / dist.rolling(window).std()

    bull_confirm = df["close"] > df["open"]
    bear_confirm = df["close"] < df["open"]

    long_cond = rising_edge((z < -z_thresh) & bull_confirm)
    short_cond = rising_edge((z > z_thresh) & bear_confirm)

    signal = pd.Series(0, index=df.index)
    signal[long_cond] = 1
    signal[short_cond] = -1
    return signal


# ── Rule family C: trend-following pullback + continuation ──────────────

def signal_trend_pullback(df: pd.DataFrame, fast: int = 20, slow: int = 100, atr_mult: float = 0.3) -> pd.Series:
    ema_fast, ema_slow = ema(df["close"], fast), ema(df["close"], slow)
    a = atr(df, 14)
    uptrend, downtrend = ema_fast > ema_slow, ema_fast < ema_slow
    near_fast_ema = (df["close"] - ema_fast).abs() < atr_mult * a

    long_cond = rising_edge(uptrend & near_fast_ema & (df["close"] > df["open"]) & (df["close"] > ema_fast))
    short_cond = rising_edge(downtrend & near_fast_ema & (df["close"] < df["open"]) & (df["close"] < ema_fast))

    signal = pd.Series(0, index=df.index)
    signal[long_cond] = 1
    signal[short_cond] = -1
    return signal


# ── DSP diagnostic: rolling autocorrelation + one-shot FFT ──────────────

def dsp_diagnostic(df: pd.DataFrame, horizons: list[int]) -> None:
    print("\n" + "=" * 64)
    print("  DSP DIAGNOSTIC (exploratory only — not a trading rule)")
    print("=" * 64)

    ret = df["close"].pct_change()
    lag1 = ret.shift(1)
    window = 60
    roll_cov = ret.rolling(window).cov(lag1)
    roll_var = lag1.rolling(window).var()
    autocorr = (roll_cov / roll_var).clip(-1, 1)

    fwd_by_horizon = {h: df["close"].shift(-h) / df["close"] - 1.0 for h in horizons}
    print(f"\nRolling {window}-bar lag-1 return autocorrelation vs forward return "
          f"(does momentum(+)/mean-reversion(-) predict what happens next?):")
    valid = autocorr.dropna()
    pos_regime = valid > 0.05
    neg_regime = valid < -0.05
    for h, fwd in fwd_by_horizon.items():
        f = fwd.reindex(valid.index)
        pos_mean = f[pos_regime].mean() * 100
        neg_mean = f[neg_regime].mean() * 100
        print(f"  h={h:>2}min | avg fwd return when autocorr>+0.05: {pos_mean:+.4f}% "
              f"| when autocorr<-0.05: {neg_mean:+.4f}%")

    # One-shot FFT on log returns — a coarse "is there an obvious dominant
    # cycle" check, not a rolling feature (too expensive/noisy at 1-min
    # resolution to be worth it without this diagnostic justifying it first).
    log_ret = np.log(df["close"]).diff().dropna().values
    n = min(len(log_ret), 200_000)
    sample = log_ret[-n:]
    spectrum = np.abs(np.fft.rfft(sample - sample.mean()))
    freqs = np.fft.rfftfreq(n, d=1.0)  # cycles per bar (1-minute bars)
    top = np.argsort(spectrum)[-6:][::-1]
    top = top[freqs[top] > 0]  # drop the DC/near-zero component
    print(f"\nOne-shot FFT on last {n:,} 1-min log-returns — top periodicities by power:")
    for idx in top[:5]:
        period_min = 1.0 / freqs[idx]
        print(f"  period ~ {period_min:,.1f} min | relative power {spectrum[idx]/spectrum.max():.3f}")
    print("  (context: with no true cycle, expect power spread ~evenly across "
          "frequencies — a spike here is a lead, not proof; needs the same "
          "train/validation discipline as any other feature before trusting it.)")


# ── Orchestration ─────────────────────────────────────────────────────────

STRATEGIES = {
    "A_momentum_breakout": signal_momentum_breakout,
    "B_mean_reversion": signal_mean_reversion,
    "C_trend_pullback": signal_trend_pullback,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()

    df = load_train_slice(args.symbol)
    bh_return = buy_and_hold_return_pct(df["close"])
    print(f"Buy & hold over TRAIN slice: {bh_return:+.2f}%")
    print(f"Round-trip cost assumed per trade: {(ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST)*100:.3f}%\n")

    signals = {name: fn(df) for name, fn in STRATEGIES.items()}
    for name, sig in signals.items():
        n_long, n_short = int((sig == 1).sum()), int((sig == -1).sum())
        print(f"{name}: {n_long} long signals, {n_short} short signals")
    print()

    header = (f"{'strategy':<24}{'horizon':>8}{'n_trades':>10}{'win%':>8}"
              f"{'PF':>8}{'expectancy%':>13}{'naive_ret%':>12}{'sharpe~':>9}")
    print(header)
    print("-" * len(header))

    for horizon in LABEL_HORIZON_CANDIDATES:
        for name, sig in signals.items():
            m = evaluate_signal(df["close"], sig, horizon)
            if m.get("n_trades", 0) == 0:
                print(f"{name:<24}{horizon:>8}{'(no trades)':>10}")
                continue
            print(f"{name:<24}{horizon:>8}{m['n_trades']:>10}{m['win_rate_pct']:>8.1f}"
                  f"{m['profit_factor']:>8.3f}{m['expectancy_pct']:>13.5f}"
                  f"{m['total_naive_return_pct']:>12.2f}{m['sharpe_like']:>9.4f}")
        # null baseline at this horizon, sized to the busiest rule for a fair-ish comparison
        busiest_n = max((signals[n] != 0).sum() for n in signals)
        null = null_baseline(df["close"], int(busiest_n), horizon)
        if null.get("n_trades", 0) > 0:
            print(f"{'NULL(random)':<24}{horizon:>8}{null['n_trades']:>10}{null['win_rate_pct']:>8.1f}"
                  f"{null['profit_factor']:>8.3f}{null['expectancy_pct']:>13.5f}"
                  f"{null['total_naive_return_pct']:>12.2f}{null['sharpe_like']:>9.4f}")
        print()

    dsp_diagnostic(df, LABEL_HORIZON_CANDIDATES)

    print("\nReminder: naive_ret% is a summed, unsized, overlap-ignoring screen "
          "(see simple_engine.py docstring) — it tells you whether a signal beats "
          "costs and the random-entry null on TRAIN, nothing about realistic "
          "portfolio P&L. A strategy worth pursuing goes to the real walk-forward "
          "engine (SPEC.md section 8) next, on VALIDATION, not more TRAIN tuning.")


if __name__ == "__main__":
    main()
