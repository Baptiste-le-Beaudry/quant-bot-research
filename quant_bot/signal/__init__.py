"""
quant_bot.signal — IA #2: "is there a statistical edge to enter now?"
(SPEC.md section 6/7). Predicts P(forward return beats transaction costs)
per SPEC.md section 6. Model tier progression (logistic -> random forest ->
gradient boosting -> neural net) and promotion criteria are in SPEC.md
section 7 — each tier must beat the previous tier's validated out-of-sample
Sharpe before being adopted. Not implemented yet.
"""
