"""Versioned per-platform cost configurations (harness v1.1).

Every numeric value carries its source. ``verified=False`` marks an assumption,
a secondary figure, or an official figure applied outside what was measured.
Primary source since v1.1: ``docs/agents/venues/VENUES_500CAD_2026-10-06.md``
and ``docs/agents/venues/venues_costs_2026-10-06.csv`` (T-004, read 2026-10-06).

Conventions
-----------
* ``fee_pct``, ``half_spread_pct``, ``slippage_pct``: **per side**, fractions
  (0.00075 = 0.075 %), charged on each fill's notional. When a measured quote
  already includes the platform fee (Jupiter ``/order``), the fee is carried
  inside ``half_spread_pct`` and ``fee_pct`` is 0 -- never both (review C3).
* ``impact_pct_per_10k_usd``: linear impact per side = coef * notional_usd / 10_000.
* ``fixed_fee_usd_per_order``: charged on every fill (entry and exit), USD.
* ``min_order_usd``: fills below this notional are refused (trade skipped).
* Funding ramp (account level, once): ``funding_conversion_pct`` per direction
  (CAD -> quote asset at start, quote -> CAD at the end) and
  ``funding_fixed_cad`` (fixed CAD fees over the whole in+out ramp).
* ``symbols``: tradable symbols (None = all).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Sourced:
    value: float
    source: str
    verified: bool = True

    def __float__(self) -> float:  # pragma: no cover - convenience
        return float(self.value)


ZERO_NA = Sourced(0.0, "not applicable", True)

# USD per CAD: USDC-CAD = 1.42075 (Coinbase public spot, 2026-10-06, T-004) -> 1 / 1.42075
USD_PER_CAD = Sourced(round(1 / 1.42075, 6), "docs/agents/venues/VENUES_500CAD_2026-10-06.md: "
                                             "USDC-CAD 1.42075 (Coinbase spot 2026-10-06) -> 0.703854", True)


@dataclass(frozen=True)
class PlatformCosts:
    name: str
    version: str
    quote_ccy: str
    fee_pct: Sourced
    half_spread_pct: Sourced
    slippage_pct: Sourced = ZERO_NA
    impact_pct_per_10k_usd: Sourced = ZERO_NA
    fixed_fee_usd_per_order: Sourced = ZERO_NA
    min_order_usd: Sourced = ZERO_NA
    funding_conversion_pct: Sourced = ZERO_NA
    funding_fixed_cad: Sourced = ZERO_NA
    symbols: Optional[frozenset] = None
    per_symbol_half_spread_pct: dict = field(default_factory=dict)
    per_symbol_fee_pct: dict = field(default_factory=dict)
    notes: str = ""

    def supports(self, symbol: str) -> bool:
        return self.symbols is None or symbol in self.symbols

    def side_cost_pct(self, symbol: str, notional_usd: float | None = None) -> float:
        """Proportional cost per side (fraction), impact included when a notional is given."""
        hs = self.per_symbol_half_spread_pct.get(symbol, self.half_spread_pct).value
        fee = self.per_symbol_fee_pct.get(symbol, self.fee_pct).value
        c = fee + hs + self.slippage_pct.value
        if notional_usd is not None:
            c += self.impact_pct_per_10k_usd.value * notional_usd / 10_000.0
        return c

    def round_trip_pct(self, symbol: str, notional_usd: float | None = None) -> float:
        return 2.0 * self.side_cost_pct(symbol, notional_usd)

    def restrict(self, name: str, symbols) -> "PlatformCosts":
        return dataclasses.replace(self, name=name, symbols=frozenset(symbols))

    def describe(self) -> list[dict]:
        rows = []
        for k in ("fee_pct", "half_spread_pct", "slippage_pct", "impact_pct_per_10k_usd",
                  "fixed_fee_usd_per_order", "min_order_usd", "funding_conversion_pct", "funding_fixed_cad"):
            s = getattr(self, k)
            rows.append({"platform": self.name, "version": self.version, "param": k, "value": s.value,
                         "source": s.source, "verified": s.verified})
        for label, d in (("half_spread_pct", self.per_symbol_half_spread_pct), ("fee_pct", self.per_symbol_fee_pct)):
            for sym, s in d.items():
                if self.supports(sym):
                    rows.append({"platform": self.name, "version": self.version, "param": f"{label}[{sym}]",
                                 "value": s.value, "source": s.source, "verified": s.verified})
        return rows


_VEN = "docs/agents/venues/VENUES_500CAD_2026-10-06.md (T-004)"
_VEN_CSV = "docs/agents/venues/venues_costs_2026-10-06.csv"
_SOL, _BTC, _ETH = "SOLUSDT", "BTCUSDT", "ETHUSDT"
_SYMBOLS_ALL9 = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
                           "LINKUSDT", "LTCUSDT", "BNBUSDT"})

# --- Jupiter -----------------------------------------------------------------
_JUP_TX = Sourced(0.01, f"{_VEN} 1.1: base fee ~0.0006 USD + priority p90 0.003-0.006 USD/swap (RPC, "
                        "2026-10-06); 0.01 USD kept as a rounded-up allowance (jupiter_paper.py tx_fee_usd). "
                        "Crash-time priority spikes and failed tx NOT modelled", False)
_JUP_MIN = Sourced(0.0, f"{_VEN}: no minimum (gasless route ~10 USD min, not used)", True)
_JUP_IMPACT = Sourced(0.0, f"{_VEN}: quotes flat at 50 and 165 USD (3 snapshots, one day); "
                           "not representative of crashes", False)
# Ramp CAD <-> USDC (review C2): 0.8-1.0 % FX in+out total -> upper bound 0.5 %/direction, + 10 CAD Interac withdrawal
_RAMP_PCT = Sourced(0.005, f"{_VEN} 1.4: 'environ 0,8-1,0 % de frais de change crypto' in+out -> "
                           "upper bound 1.0 % total = 0.5 %/direction (Kraken stablecoin 0.20 %/side or "
                           "Wealthsimple 0.5 %; crypto withdrawal network fees not verified)", False)
_RAMP_FIXED = Sourced(10.0, f"{_VEN} 1.4: Kraken CAD withdrawal by Interac 10 CAD "
                            "(support.kraken.com/ca/articles/4412259063444)", True)
_SOL_ORDER_QUOTE = Sourced(0.000205, f"{_VEN} 1.1: /swap/v2/order buy-then-sell quote RT measured 0.037-0.041 % "
                                     "at 50 and 165 USD, 2 bps fee INCLUDED in the quote -> 0.041 %/2 per side", True)
_BUILD_QUOTE = Sourced(0.0001, f"{_VEN} 1.1 / {_VEN_CSV}: /build (Metis router, no platform fee) AR "
                               "~0.01-0.03 %; measured on SOL only (lite-api quote -0.006..+0.005 %) -> "
                               "0.02 % RT = 0.01 %/side; cbBTC/WETH quotes NOT measured; MEV/landing at our "
                               "risk, not priced", False)
_BTCETH_FEE = Sourced(0.0010, f"{_VEN} 1.1: Jupiter /order fee 'everything else' (incl. cbBTC, WETH) "
                              "10 bps per swap (developers.jup.ag/docs/swap/fees)", True)
_BTCETH_SPREAD = Sourced(0.0, f"{_VEN_CSV}: cbBTC/WETH quote spread not measured 2026-10-06 "
                              "(0.00-0.04 % on 2026-10-05) -> 0 (optimistic)", False)

_JUP_COMMON = dict(quote_ccy="USDC", impact_pct_per_10k_usd=_JUP_IMPACT, fixed_fee_usd_per_order=_JUP_TX,
                   min_order_usd=_JUP_MIN, funding_conversion_pct=_RAMP_PCT, funding_fixed_cad=_RAMP_FIXED)

JUPITER_ORDER = PlatformCosts(
    name="jupiter_order", version="1.1",
    fee_pct=_BTCETH_FEE, half_spread_pct=_BTCETH_SPREAD,
    per_symbol_fee_pct={_SOL: Sourced(0.0, "SOL fee (2 bps) is inside the measured /order quote", True)},
    per_symbol_half_spread_pct={_SOL: _SOL_ORDER_QUOTE},
    symbols=frozenset({_SOL, _BTC, _ETH}), **_JUP_COMMON,
    notes="Jupiter Swap v2 /order (Ultra, private submission). SOL: measured quote incl. fee; "
          "cbBTC/WETH: 10 bps fee, spread unmeasured.")

PLATFORMS: dict[str, PlatformCosts] = {
    "research_0p14": PlatformCosts(
        name="research_0p14", version="1.0", quote_ccy="USD",
        fee_pct=Sourced(0.0007, "scripts/strategy_a/exit_realism_check.py COST=0.0014 round trip "
                                "(research reference, not a real venue) -> 0.07 %/side"),
        half_spread_pct=Sourced(0.0, "included in the 0.14 % reference"),
        notes="Reference used by the research ledger and the reconciliation test."),
    "jupiter_sol": JUPITER_ORDER.restrict("jupiter_sol", {_SOL}),
    "jupiter_sol_stress": dataclasses.replace(
        JUPITER_ORDER.restrict("jupiter_sol_stress", {_SOL}),
        per_symbol_half_spread_pct={_SOL: Sourced(0.0004, "v1.0 value kept as stress: 2 bps fee + 2 bps "
                                                         "half-spread per side (double counts the fee) = 0.08 % RT",
                                                  False)}),
    "jupiter_order_btceth": JUPITER_ORDER.restrict("jupiter_order_btceth", {_BTC, _ETH}),
    "jupiter_order": JUPITER_ORDER,
    "jupiter_build": PlatformCosts(
        name="jupiter_build", version="1.1",
        fee_pct=Sourced(0.0, f"{_VEN}: /swap/v2/build 'Swap fees: No' (developers.jup.ag/docs/swap)", True),
        half_spread_pct=_BUILD_QUOTE, symbols=frozenset({_SOL, _BTC, _ETH}), **_JUP_COMMON,
        notes="Router path without platform fee; we land the transaction ourselves (more MEV/failure "
              "exposure, not priced)."),
    "propr_0p045": PlatformCosts(
        name="propr_0p045", version="1.1", quote_ccy="USD",
        fee_pct=Sourced(0.00045, f"{_VEN} 2.1 / {_VEN_CSV}: Propr rulebook says Hyperliquid fees passed at "
                                 "cost, tier-0 taker 0.045 % -- contradicts OpenAPI example 0.075 %", False),
        half_spread_pct=Sourced(0.0001, "fallback 2 bps full spread (funded_shadow_crypto.py)", False),
        per_symbol_half_spread_pct={},  # filled below
        slippage_pct=Sourced(0.0001, "paper_trading_bot/scripts/funded_shadow_crypto.py SLIPPAGE=0.0001 "
                                     "per side (allowance, not measured)", False),
        symbols=_SYMBOLS_ALL9,
        notes="WARNING: per-trade cost only. The account replay does NOT simulate Propr challenge rules "
              "(5 % daily loss, 8 % trailing DD on unrealized equity, 50 USD fee, funding) -> it does not "
              "evaluate path B."),
    "kraken_ca_maker": PlatformCosts(
        name="kraken_ca_maker", version="1.1", quote_ccy="CAD",
        fee_pct=Sourced(0.0040, f"{_VEN}: Kraken Pro CA maker 0.40 % (kraken.com/features/fee-schedule)", True),
        half_spread_pct=Sourced(0.0, "maker fill at own limit price; fill rate / adverse selection "
                                     "NOT modelled (optimistic)", False),
        min_order_usd=Sourced(0.0, "Kraken per-asset minimums not verified (T-004); not modelled", False),
        funding_fixed_cad=_RAMP_FIXED, symbols=_SYMBOLS_ALL9,
        notes="Maker on both legs is an upper bound: a stop or time exit is usually taker."),
    "kraken_ca_taker": PlatformCosts(
        name="kraken_ca_taker", version="1.1", quote_ccy="CAD",
        fee_pct=Sourced(0.0080, f"{_VEN}: Kraken Pro CA taker 0.80 % (kraken.com/features/fee-schedule)", True),
        half_spread_pct=Sourced(0.0, "Kraken CAD-pair spread not measured -> 0 (optimistic)", False),
        min_order_usd=Sourced(0.0, "Kraken per-asset minimums not verified (T-004); not modelled", False),
        funding_fixed_cad=_RAMP_FIXED, symbols=_SYMBOLS_ALL9),
}

# Propr: logged Hyperliquid top-of-book full spreads (bps) 2026-10-04 -> half-spread per side.
_PROPR_SPREAD_BPS = {"BTC": 0.12, "ETH": 0.37, "SOL": 0.82, "XRP": 0.66, "DOGE": 1.14,
                     "ADA": 1.52, "LINK": 0.70, "LTC": 0.99, "BNB": 0.38}
_PROPR_HS = {f"{k}USDT": Sourced(v / 2e4, "scripts/funded_backtest_propr.py SPREAD_BPS (Hyperliquid "
                                          "median full spread logged 2026-10-04) / 2", True)
             for k, v in _PROPR_SPREAD_BPS.items()}
PLATFORMS["propr_0p045"] = dataclasses.replace(PLATFORMS["propr_0p045"], per_symbol_half_spread_pct=_PROPR_HS)
PLATFORMS["propr_0p075"] = dataclasses.replace(
    PLATFORMS["propr_0p045"], name="propr_0p075",
    fee_pct=Sourced(0.00075, "Propr OpenAPI https://propr.xyz/openapi.json tradingFeeRate example 0.00075 "
                             f"(maker = taker); {_VEN} 2.1: only an example, contradicts rulebook -> unverified",
                    False))

# --- US equities (v1.3, Exp 62 / T-039) ---------------------------------------
# Official pages read 2026-10-07 with curl (WebFetch gets 403 on IBKR):
_IBKR_STK = "interactivebrokers.ca/en/pricing/commissions-stocks.php (read 2026-10-07)"
_IBKR_FX = "interactivebrokers.ca/en/pricing/commissions-spot-currencies.php (read 2026-10-07)"
_EQ_SPREAD = Sourced(0.0001, "Exp-62 preregistration fallback 0.02 % RT (Dukascopy cache is BID only, real "
                             "NBBO spread not measured)", False)
_SEC_FEE = Sourced(0.0000103, f"{_IBKR_STK}: SEC Transaction Fee USD 0.0000206 * value of sales -> charged on "
                              "the exit only = 0.00103 %/side on average", True)
# IBKR FX: 0.20 bp * value, min USD 2.00 per conversion -> on ~350 USD the minimum binds.
_IBKR_FX_PCT = Sourced(0.00002, f"{_IBKR_FX}: 0.20 basis point * trade value (tier I)", True)
_IBKR_FX_FIXED = Sourced(round(2 * 2.00 / USD_PER_CAD.value, 2), f"{_IBKR_FX}: minimum USD 2.00 per conversion, "
                                                                 "CAD->USD at start + USD->CAD at the end", True)
EQUITY_PLATFORMS: dict[str, PlatformCosts] = {
    "ibkr_ca_fixed": PlatformCosts(
        name="ibkr_ca_fixed", version="1.3", quote_ccy="USD",
        fee_pct=_SEC_FEE, half_spread_pct=_EQ_SPREAD,
        fixed_fee_usd_per_order=Sourced(1.00, f"{_IBKR_STK}: Fixed USD 0.005/share, minimum USD 1.00 per order, "
                                              "maximum 1 % of trade value; exact as a flat 1.00 USD for "
                                              "100 USD <= notional <= 200 * share price (always the case at 100-"
                                              "20 000 USD here); fractional shares: 'same commission rates as "
                                              "whole share trades'", True),
        min_order_usd=Sourced(1.0, "interactivebrokers.ca/en/trading/fractional-trading.php: fractional US "
                                   "stocks 'starting from just USD 1' (fractional orders via the TWS API and "
                                   "stop orders on fractions NOT verified)", True),
        funding_conversion_pct=_IBKR_FX_PCT, funding_fixed_cad=_IBKR_FX_FIXED,
        notes="IBKR Canada, US stocks, Fixed plan (regulatory/exchange fees included except SEC fee). "
              "Below 100 USD notional the 1 % cap binds (not modelled: overstates cost). Market data: "
              "'US Real-Time Non Consolidated Streaming Quotes' complimentary (research-news-marketdata.php)."),
    "ibkr_ca_tiered": PlatformCosts(
        name="ibkr_ca_tiered", version="1.3", quote_ccy="USD",
        fee_pct=_SEC_FEE, half_spread_pct=_EQ_SPREAD,
        fixed_fee_usd_per_order=Sourced(0.35, f"{_IBKR_STK}: Tiered USD 0.0035/share (<= 300 000 shares/month), "
                                              "minimum USD 0.35 per order, cap 0.5 % of trade value; flat 0.35 "
                                              "exact for 70 USD <= notional <= 100 * share price", True),
        slippage_pct=Sourced(0.00002, "Tiered adds exchange (liquidity-removing ~USD 0.003/share), clearing and "
                                      "pass-through fees: per-share, schedule not read -> 0.002 %/side allowance "
                                      "(~USD 0.003/share on a 150 USD share)", False),
        min_order_usd=Sourced(1.0, "same as ibkr_ca_fixed (fractional from USD 1)", True),
        funding_conversion_pct=_IBKR_FX_PCT, funding_fixed_cad=_IBKR_FX_FIXED,
        notes="IBKR Canada, US stocks, Tiered plan."),
    "zero_commission_ca": PlatformCosts(
        name="zero_commission_ca", version="1.3", quote_ccy="USD",
        fee_pct=Sourced(0.0, "Questrade ($0 commissions on stocks and ETFs, questrade.com/pricing/self-directed-"
                             "investing/fees), NBDB (nbdb.ca/pricing.html), Wealthsimple (wealthsimple.com/en-ca/"
                             "pricing): $0 commission, read 2026-10-07", True),
        half_spread_pct=_EQ_SPREAD,
        funding_conversion_pct=Sourced(0.015, "wealthsimple.com/en-ca/pricing: USD account, CAD->USD 1.5 % (< 10 000 "
                                              "USD) per conversion (NBDB: 1.70 %); per direction", True),
        notes="HYPOTHETICAL venue: no zero-commission Canadian broker with a retail order API was found "
              "(Questrade API: 'If you are a Questrade partner developer, you can also use the API to place "
              "trades', questrade.com/api/documentation/getting-started; Wealthsimple/NBDB: no public API "
              "documented, NOT verified). Wealthsimple USD account needs a paid plan (10 CAD/month, not "
              "modelled)."),
    "cfd_darwinex_assumed": PlatformCosts(
        name="cfd_darwinex_assumed", version="1.3", quote_ccy="USD",
        fee_pct=Sourced(0.0, "per-share commission set per symbol by with_per_share_fee()", True),
        half_spread_pct=Sourced(0.0001, "Darwinex does not publish stock-CFD spreads (help.darwinex.com/execution-"
                                        "costs refers to a JS table) -> 0.02 % RT assumed", False),
        notes="Stock CFDs (Darwinex: ~800 US stock CFDs, help.darwinex.com/assets-available). Commission "
              "USD 0.04/share/side and swap 6.5 %/yr are internal assumptions (paper_trading_bot/scripts/"
              "darwinex_shadow_equity.py), NOT verified. Availability to a Quebec resident NOT verified "
              "(no Canadian registration found; IBKR CFD page redirects .ca -> .co.uk; OANDA Canada lists no "
              "single-stock CFD)."),
}
DARWINEX_USD_PER_SHARE = Sourced(0.04, "paper_trading_bot/scripts/darwinex_shadow_equity.py COMMISSION_PER_SHARE "
                                       "(origin not found, NOT verified)", False)
DARWINEX_SWAP_ANNUAL = Sourced(0.065, "scripts/funded_backtest_darwinex.py 6.5 %/yr per night (NOT verified)", False)
PLATFORMS.update(EQUITY_PLATFORMS)


def with_per_share_fee(plat: PlatformCosts, usd_per_share: float, prices: dict, source: str) -> PlatformCosts:
    """Per-share commission expressed as a per-symbol fee_pct = usd_per_share / reference price
    (v1.3; ``prices`` = one reference price per symbol, e.g. the median entry price)."""
    fees = {s: Sourced(usd_per_share / float(p), f"{source}; USD {usd_per_share}/share / ref. price {float(p):.2f}",
                       False)
            for s, p in prices.items()}
    return dataclasses.replace(plat, per_symbol_fee_pct=fees)


# Platforms reported in the standard tables (aliases jupiter_order / jupiter_sol_stress kept for stress use)
TABLE_PLATFORMS = ["research_0p14", "jupiter_sol", "jupiter_build", "jupiter_order_btceth",
                   "propr_0p045", "propr_0p075", "kraken_ca_maker", "kraken_ca_taker"]


def get_platform(name: str) -> PlatformCosts:
    try:
        return PLATFORMS[name]
    except KeyError as exc:
        raise KeyError(f"unknown platform {name!r}; known: {sorted(PLATFORMS)}") from exc
