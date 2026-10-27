"""quant_bot/strategy_c/features.py — STRATEGY_ID = C causal feature
computation (docs/strategy_c/STRATEGY_C_SPEC.md's C8: 7 features
maximum, interpretable, no ML yet). Every function here is causal BY
CONSTRUCTION: at output index t, only inputs with timestamp <= t are
used (rolling/cumulative/backward-merge operations only, never a
centered or forward-looking window). Verified by
tests/strategy_c/test_causality.py's synthetic future-data-injection
tests (per the mandate's C7 explicit requirement) -- run those before
trusting any feature computed here.

Aggressor classification (C9): the QUOTE TEST -- a trade is classified
buyer-initiated if its price >= the PREVAILING ask (the most recent
quote at or before the trade's own timestamp, via merge_asof backward,
never a quote that arrived after the trade), seller-initiated if <=
the prevailing bid, and AMBIGUOUS (not assumed either way) otherwise.
Documented explicitly per the mandate: "ne suppose jamais qu'un trade
au-dessus du dernier prix = buyer initiated" -- this uses the quote
context, not the tick rule (previous trade price), as the primary
method.
"""
import numpy as np
import pandas as pd


def attach_prevailing_quote(trades: pd.DataFrame, quotes: pd.DataFrame,
                             bid_col: str = "bid_px_00", ask_col: str = "ask_px_00",
                             bid_sz_col: str = "bid_sz_00", ask_sz_col: str = "ask_sz_00") -> pd.DataFrame:
    """Attach the PREVAILING (most recent, at-or-before) quote to each trade via a backward
    merge_asof -- causal by construction: a trade can never see a quote that arrived after it."""
    t = trades.sort_index()
    q = quotes.sort_index()[[bid_col, ask_col, bid_sz_col, ask_sz_col]]
    merged = pd.merge_asof(t, q, left_index=True, right_index=True, direction="backward")
    return merged


def classify_aggressor(trades_with_quotes: pd.DataFrame, price_col: str = "price",
                        bid_col: str = "bid_px_00", ask_col: str = "ask_px_00") -> pd.Series:
    """Quote test: BUY if price >= prevailing ask, SELL if price <= prevailing bid, else AMBIGUOUS.
    Returns a categorical Series -- never silently defaults an ambiguous trade to BUY or SELL."""
    price = trades_with_quotes[price_col]
    ask = trades_with_quotes[ask_col]
    bid = trades_with_quotes[bid_col]
    has_quote = bid.notna() & ask.notna()
    result = pd.Series("AMBIGUOUS", index=trades_with_quotes.index, dtype="object")
    result[has_quote & (price >= ask)] = "BUY"
    result[has_quote & (price <= bid)] = "SELL"
    result[~has_quote] = "MISSING"  # explicitly distinct from AMBIGUOUS -- no quote context at all
    return result


def _uncrossed_mask(quotes: pd.DataFrame, bid_col: str = "bid_px_00", ask_col: str = "ask_px_00") -> pd.Series:
    """Both sides positive AND not crossed (bid <= ask). A crossed quote (bid > ask, ~0.0007% of
    rows per the C5 data audit) is a bad/transient tick, not a real tradeable state -- excluded
    (MISSING) from every feature derived from price/size at that timestamp, never left in to
    silently produce a sign-flipped imbalance or negative spread."""
    bid, ask = quotes[bid_col], quotes[ask_col]
    return (bid > 0) & (ask > 0) & (bid <= ask)


def quote_imbalance(quotes: pd.DataFrame, bid_sz_col: str = "bid_sz_00", ask_sz_col: str = "ask_sz_00",
                     bid_col: str = "bid_px_00", ask_col: str = "ask_px_00") -> pd.Series:
    """QI = (bid_size - ask_size) / (bid_size + ask_size). Purely a function of the CURRENT quote
    snapshot -- no rolling window, causal trivially."""
    bid_sz, ask_sz = quotes[bid_sz_col], quotes[ask_sz_col]
    denom = bid_sz + ask_sz
    valid = (denom > 0) & _uncrossed_mask(quotes, bid_col, ask_col)
    return ((bid_sz - ask_sz) / denom).where(valid)  # MISSING (not 0/False) when empty or crossed


def spread_pct(quotes: pd.DataFrame, bid_col: str = "bid_px_00", ask_col: str = "ask_px_00") -> pd.Series:
    """(ask - bid) / mid. MISSING (not 0) if either side is absent/non-positive/crossed."""
    bid, ask = quotes[bid_col], quotes[ask_col]
    valid = _uncrossed_mask(quotes, bid_col, ask_col)
    mid = (bid + ask) / 2.0
    return ((ask - bid) / mid).where(valid)


def trade_flow_imbalance(trades_classified: pd.DataFrame, window: str = "60s",
                          size_col: str = "size", aggressor_col: str = "aggressor") -> pd.Series:
    """Rolling (time-based, causal) aggressive-buy-volume minus aggressive-sell-volume, normalized
    by total classified volume in the window. AMBIGUOUS/MISSING trades are excluded from both the
    numerator and the volume-weighted denominator (not silently counted as neutral/zero)."""
    buy_vol = trades_classified[size_col].where(trades_classified[aggressor_col] == "BUY", 0.0)
    sell_vol = trades_classified[size_col].where(trades_classified[aggressor_col] == "SELL", 0.0)
    classified_vol = trades_classified[size_col].where(trades_classified[aggressor_col].isin(["BUY", "SELL"]), 0.0)
    # .rolling(window, closed="left") would exclude the CURRENT row's own trade from its own signal
    # value -- deliberately using closed="right" (default, includes current row) since the trade
    # AT time t is itself already known/causal at t (matches this project's own "bar t's own close
    # is known at t" convention, documented in docs/strategy_b/funding/STRATEGY_B_FUNDING_SPEC.md).
    roll_buy = buy_vol.rolling(window).sum()
    roll_sell = sell_vol.rolling(window).sum()
    roll_total = classified_vol.rolling(window).sum()
    return ((roll_buy - roll_sell) / roll_total).where(roll_total > 0)


def trade_intensity(trades: pd.DataFrame, short_window: str = "60s", baseline_window: str = "20min") -> pd.Series:
    """Relative (not absolute) intensity: recent trade COUNT over short_window, divided by the
    trailing average count over the same short_window length within baseline_window -- relative
    thresholds, matching this project's own established preference (realized_vol_ratio-style) over
    raw absolute counts that don't transfer across regimes/times of day."""
    count_1 = pd.Series(1, index=trades.index)
    short_count = count_1.rolling(short_window).sum()
    # baseline: rolling mean of the short-window count itself, over a longer trailing window
    baseline = short_count.rolling(baseline_window).mean()
    return (short_count / baseline).where(baseline > 0)


def short_term_volatility(trades: pd.DataFrame, price_col: str = "price", window: str = "60s") -> pd.Series:
    """Causal rolling realized volatility of trade-price log returns."""
    log_ret = np.log(trades[price_col]).diff()
    return log_ret.rolling(window).std()


def distance_to_session_vwap(trades: pd.DataFrame, price_col: str = "price", size_col: str = "size",
                              session_tz: str = "America/New_York") -> pd.Series:
    """Distance to the SESSION-CUMULATIVE VWAP so far (resets each session-day, uses only trades up
    to and including the current one within that session -- never the full session's future volume,
    which would be a lookahead leak this project has explicitly guarded against before, e.g. the
    B_INDEX session-VWAP discussion in docs/strategy_b/index/)."""
    ny_index = trades.index.tz_convert(session_tz)
    session_date = pd.Series(ny_index.date, index=trades.index)
    notional = trades[price_col] * trades[size_col]
    cum_notional = notional.groupby(session_date).cumsum()
    cum_size = trades[size_col].groupby(session_date).cumsum()
    session_vwap = cum_notional / cum_size
    return (trades[price_col] - session_vwap) / session_vwap


def short_term_price_impact(trades_classified: pd.DataFrame, price_col: str = "price",
                             size_col: str = "size", aggressor_col: str = "aggressor",
                             window: str = "60s") -> pd.Series:
    """Price change per unit of (net) aggressive flow over the trailing window -- a direct
    microstructure IMPACT measure, distinct from the PRESSURE measures above (#1/#2)."""
    price_change = trades_classified[price_col] - trades_classified[price_col].rolling(window).apply(
        lambda x: x[0] if len(x) else np.nan, raw=True)
    buy_vol = trades_classified[size_col].where(trades_classified[aggressor_col] == "BUY", 0.0)
    sell_vol = trades_classified[size_col].where(trades_classified[aggressor_col] == "SELL", 0.0)
    net_flow = (buy_vol - sell_vol).rolling(window).sum()
    return (price_change / net_flow).where(net_flow.abs() > 0)
