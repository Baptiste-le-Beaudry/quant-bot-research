"""
quant_bot.live — paper and live execution (SPEC.md section 2, Phase 12).

exchange_adapter.py defines the venue-agnostic ExchangeAdapter contract;
binance_adapter.py implements it for Binance USDT-M Futures, which is the
data/research venue but explicitly NOT a confirmed-legal live-execution
venue for Canadian residents — its order/account methods raise
NotImplementedError on purpose. A paper-trading engine and any live adapter
are not implemented yet: backtest + walk-forward must clear the
buy-and-hold bar (SPEC.md section 1) before this is built, and a
compliant execution venue must be confirmed before EXCHANGE_EXECUTION in
quant_bot.config is set to anything.
"""
