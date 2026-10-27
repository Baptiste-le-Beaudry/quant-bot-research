"""
quant_bot.features — feature engine (SPEC.md section 5).

Not implemented yet: waiting on spec review, per SPEC.md section 13. When
built, this package holds one module per family (momentum, volatility,
volume_orderflow, structure, dsp) plus pipeline.py, which assembles them and
runs the mandatory redundancy pruning (drop any feature with |corr| > 0.9 to
an already-kept feature) before anything reaches a model.
"""
