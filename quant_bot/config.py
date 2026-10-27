"""
quant_bot.config — central settings. Mirrors SPEC.md's decisions so there is
exactly one place that encodes "what market, what costs, what risk rules" —
every other module reads from here rather than hardcoding numbers.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Market (SPEC.md section 2) ──────────────────────────────────────────
# Binance USDT-M Futures is the DATA/RESEARCH venue — decided and confirmed.
# It is explicitly NOT assumed to be a legal live-execution venue: Binance
# withdrew from Canada in 2023 and cannot legally onboard Canadian residents
# (Quebec included) for trading, derivatives especially. Public market-data
# endpoints (klines/funding/OI) don't require an account and are used freely
# for research; nothing in quant_bot.live may talk to an exchange directly —
# it goes through quant_bot.live.exchange_adapter.ExchangeAdapter, so the
# execution venue can be swapped for whatever is confirmed legal (a
# Canada-registered platform, a different jurisdiction's account, or an MT5
# CFD broker as confluence_ai_v3 used) without touching data/features/models.
DATA_EXCHANGE = "binance_usdm_futures"
EXECUTION_EXCHANGE = None   # unset on purpose — no live venue is confirmed
                             # legal yet; set only once verified (SPEC.md sec 2)
SYMBOLS       = ["BTCUSDT", "ETHUSDT"]   # BTCUSDT first; ETHUSDT is the
                                          # out-of-sample sanity check, not
                                          # traded until BTCUSDT clears the
                                          # walk-forward bar (SPEC.md sec 1)
BASE_INTERVAL = "1m"                     # everything else is derived from
                                          # this (SPEC.md section 3)

# ── Label (SPEC.md section 6) ───────────────────────────────────────────
# 10 minutes is the BASELINE default, not a locked-in choice — Phase 3's
# no-AI baseline must run the horizon-selection experiment (predictive power
# per candidate horizon) before any feature engineering effort gets spent
# optimizing around one horizon specifically. Every label/feature function
# takes horizon_min as a parameter; nothing hardcodes 10.
LABEL_HORIZON_MIN = 10
LABEL_HORIZON_CANDIDATES = [5, 10, 15, 30]

# ── Costs (SPEC.md section 9) ───────────────────────────────────────────
TAKER_FEE_PCT     = 0.0005   # 0.05% per side — confirm current fee tier
MAKER_FEE_PCT     = 0.0002   # 0.02% per side
ROUND_TRIP_FEE_PCT = TAKER_FEE_PCT * 2
SLIPPAGE_PCT_EST  = 0.0002   # placeholder until calibrated against paper
                              # trading fills (SPEC.md section 9)
COST_THRESHOLD_PCT = ROUND_TRIP_FEE_PCT + SLIPPAGE_PCT_EST

# ── Risk (SPEC.md section 11) ───────────────────────────────────────────
RISK_PCT_PER_TRADE   = 0.01   # cap; actual size is f(P_win, vol, drawdown)
MAX_DAILY_LOSS_PCT   = 0.03   # kill switch trigger
KELLY_FRACTION       = 0.25   # quarter-Kelly cap, not full Kelly

# Derived by the corrected final 9-symbol (+SOL, XRP p80, LINK p95)
# pre-HOLDOUT frontier (2026-08-24).
# These profiles change risk only; model/features/signals/stops/exits stay
# identical. None is live-enabled before forward paper validation.
RISK_PROFILES = {
    "normal": {"risk_pct": 0.015, "max_portfolio_open_risk": 0.135,
               "max_gross_exposure": 3.0, "hard_leverage_ceiling": 30.0,
               "research_validated": True, "live_enabled": False},
    "aggressive": {"risk_pct": 0.035, "max_portfolio_open_risk": 0.20,
                   "max_gross_exposure": 6.0, "hard_leverage_ceiling": 30.0,
                   "research_validated": True, "live_enabled": False},
    "max-risk": {"risk_pct": 0.08, "max_portfolio_open_risk": 0.24,
                 "max_gross_exposure": 8.0, "hard_leverage_ceiling": 30.0,
                 "research_validated": True, "live_enabled": False},
}

# ── Backtest split (SPEC.md section 8) ──────────────────────────────────
TRAIN_FRACTION      = 0.60
VALIDATION_FRACTION = 0.20
HOLDOUT_FRACTION    = 0.20    # touched once, after everything else is frozen

# ── Telegram (reused from confluence_ai_v3) ─────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Binance API keys — research/paper convenience ONLY ──────────────────
# Not used for live trading (see EXECUTION_EXCHANGE above). Historical data
# needs no key at all; these are only for a BinanceFuturesAdapter paper-mode
# session against testnet or read-only account data during development.
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
