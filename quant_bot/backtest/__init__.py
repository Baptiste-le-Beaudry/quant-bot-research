"""
quant_bot.backtest — walk-forward engine, train/validation/holdout split,
and cost model (SPEC.md sections 8-9). Walk-forward by construction, not by
afterthought: this is a direct response to confluence_ai_v3's backtest.py,
which pretrained on the entire dataset before walking through it
chronologically — a lookahead bug that inflated every headline number in
that repo until walk_forward.py (rolling train/test windows) replaced it as
the trustworthy source of truth. Not implemented yet.
"""
