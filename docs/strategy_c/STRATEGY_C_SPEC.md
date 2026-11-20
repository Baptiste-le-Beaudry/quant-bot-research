# STRATEGY C — US Equity Microstructure Specification
STRATEGY_ID = C

## 0. Objective
Discover, validate, and exploit a real statistical edge in intraday US Equity/ETF markets (starting with QQQ) using microstructure data (order flow, book imbalance, liquidity) rather than just OHLCV price action.

## 1. Scope & Constraints
- **Primary Research:** QQQ (Nasdaq-100 ETF)
- **External Generalization:** SPY (S&P 500 ETF)
- **Status:** Phase C0 (Initialization)
- **Rules:**
    - Strategy A (Crypto Mean-Reversion) is FROZEN.
    - Strategy B (Crypto Momentum/Breakout) is CLOSED.
    - Strategy C is INDEPENDENT. No shared features or logic unless explicitly justified.
    - NO ML (Machine Learning) before a raw economic drift is found.
    - NO Live execution in this mandate.

## 2. Scientific Protocol (Phased)
1. ECONOMIC HYPOTHESIS
2. DATA ACQUISITION
3. DATA AUDIT
4. CAUSAL FEATURE CHECK
5. RAW FORWARD DRIFT
6. NULL BASELINE
7. COSTS / SPREAD
8. CHEAP SCREEN
9. WALK-FORWARD
10. ONLY THEN ML
11. EXECUTION STRESS
12. SPY GENERALIZATION
13. PORTFOLIO COMPLEMENTARITY

## 3. Initial Hypothesis
"Abnormally strong and persistent buying/selling pressure in the order flow (imbalance) precedes short-term directional price movements before they are fully reflected in the mid-price."

**Key Indicators:**
- Order Flow Imbalance (OFI)
- Quote/Book Imbalance (OBI)
- Volume/Activity Intensity
- Spread/Liquidity dynamics

## 4. Documentation Policy
Every experiment must be pre-registered in `docs/strategy_c/STRATEGY_C_RESEARCH_LOG.md`.
Negative results are as valuable as positive ones.
Reproduction is mandatory before belief.
