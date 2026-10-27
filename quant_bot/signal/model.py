"""
model.py — IA #2, the entry signal model (SPEC.md sections 4/6/7).

Tier 1: logistic regression. Per SPEC.md section 7, every subsequent tier
(random forest, gradient boosting, neural net) must beat this tier's
validated out-of-sample Sharpe before being adopted — added complexity is
not assumed to be better.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from xgboost import XGBRegressor


class Tier1LogisticSignal:
    """P(forward return over horizon_min beats cost) via logistic regression
    on the redundancy-pruned feature set (quant_bot.features.pipeline).

    Features are standardized before fitting — raw features here span very
    different natural scales (e.g. realized_vol_30 ~ 1e-3 vs dist_*_atr ~
    1-50), and logistic regression's L2 penalty shrinks small-scale features
    unfairly without scaling. A first run without this step produced near-
    zero coefficients for the single highest-mutual-information feature
    from Phase 4 (docs/phase4_results.md) — exactly the symptom of this bug,
    which is why the scaler is here rather than added later "if needed"."""

    def __init__(self, feature_names: list[str]):
        self.feature_names = feature_names
        self.scaler = StandardScaler()
        self.model = LogisticRegression(max_iter=1000, class_weight="balanced")

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "Tier1LogisticSignal":
        valid = X[self.feature_names].notna().all(axis=1) & y.notna()
        X_scaled = self.scaler.fit_transform(X.loc[valid, self.feature_names])
        self.model.fit(X_scaled, y.loc[valid])
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        valid = X[self.feature_names].notna().all(axis=1)
        proba = pd.Series(np.nan, index=X.index)
        if valid.any():
            X_scaled = self.scaler.transform(X.loc[valid, self.feature_names])
            proba.loc[valid] = self.model.predict_proba(X_scaled)[:, 1]
        return proba

    def feature_importance(self) -> pd.Series:
        """Coefficient magnitude on STANDARDIZED features — comparable
        across features now that scale differences are removed. SPEC.md
        section 10 requires this check before trusting any promoted model,
        not just tier 1."""
        return pd.Series(np.abs(self.model.coef_[0]), index=self.feature_names).sort_values(ascending=False)


class Tier2RandomForestSignal:
    """Tier 2 (SPEC.md section 7): must beat tier 1's validated out-of-
    sample result to earn its extra complexity — tier 1 (docs/phase6_7_results.md)
    did not survive HOLDOUT, so the bar here is "does this show a real,
    adequately-sampled edge on VALIDATION at all," not just "beat a number."

    max_depth is capped deliberately: Phase 4's mutual-information values
    were all small (docs/phase4_results.md) — an unconstrained forest on
    noisy financial features with that little per-feature signal is a
    strong overfitting risk, not a reason to expect a bigger model finds
    more truth. No feature scaling needed (tree splits are scale-invariant,
    unlike tier 1's logistic regression)."""

    def __init__(self, feature_names: list[str], n_estimators: int = 300,
                 max_depth: int = 5, random_state: int = 42):
        self.feature_names = feature_names
        self.model = RandomForestClassifier(
            n_estimators=n_estimators, max_depth=max_depth,
            min_samples_leaf=200,  # extra guard against fitting noise given weak MI
            class_weight="balanced", random_state=random_state, n_jobs=-1,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "Tier2RandomForestSignal":
        valid = X[self.feature_names].notna().all(axis=1) & y.notna()
        self.model.fit(X.loc[valid, self.feature_names], y.loc[valid])
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        valid = X[self.feature_names].notna().all(axis=1)
        proba = pd.Series(np.nan, index=X.index)
        if valid.any():
            proba.loc[valid] = self.model.predict_proba(X.loc[valid, self.feature_names])[:, 1]
        return proba

    def feature_importance(self) -> pd.Series:
        return pd.Series(self.model.feature_importances_, index=self.feature_names).sort_values(ascending=False)


class RegressionForestSignal:
    """Option 2 (docs/phase6_summary.md): predicts the raw forward return
    directly (quant_bot.features.build.build_regression_label) instead of
    a fixed cost-threshold binary label. Motivated by realized_vol_30 /
    atr_norm dominating every classifier's feature importance so far —
    that looks like magnitude information the binary label was discarding.

    predict() returns the predicted return itself; trading logic compares
    it against a cost threshold directly (quant_bot.backtest.engine.simulate
    already does exactly this if you pass predicted return as its "proba"
    argument with threshold=cost_threshold_pct — no new engine code needed).
    Same depth/leaf regularization as Tier2RandomForestSignal, same
    rationale (Phase 4's low mutual-information values)."""

    def __init__(self, feature_names: list[str], n_estimators: int = 100,
                 max_depth: int = 5, random_state: int = 42):
        self.feature_names = feature_names
        self.model = RandomForestRegressor(
            n_estimators=n_estimators, max_depth=max_depth,
            min_samples_leaf=200, random_state=random_state, n_jobs=-1,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RegressionForestSignal":
        valid = X[self.feature_names].notna().all(axis=1) & y.notna()
        self.model.fit(X.loc[valid, self.feature_names], y.loc[valid])
        return self

    def predict(self, X: pd.DataFrame) -> pd.Series:
        valid = X[self.feature_names].notna().all(axis=1)
        pred = pd.Series(np.nan, index=X.index)
        if valid.any():
            pred.loc[valid] = self.model.predict(X.loc[valid, self.feature_names])
        return pred

    def feature_importance(self) -> pd.Series:
        return pd.Series(self.model.feature_importances_, index=self.feature_names).sort_values(ascending=False)


class Tier3GradientBoostSignal:
    """Tier 3 (SPEC.md section 7): gradient boosting on the same regression
    target as RegressionForestSignal (option 2, docs/phase6_regression_results.md
    — the first tier to show a reliably-sampled, both-directions edge on
    ETHUSDT). Per the user's explicit sequencing, this is only tried once
    the horizon (option 3) and target redesign (option 2) already showed
    something real — escalating model complexity is the last lever, not
    the first, precisely so it isn't searching for signal in noise.

    Regularized similarly to tier 2 (shallow trees, min_child_weight as the
    boosting-tree analogue of min_samples_leaf) for the same reason: Phase 4's
    mutual-information values were all small, so there's little reason to
    expect an unconstrained model finds more real structure rather than
    fitting noise harder."""

    def __init__(self, feature_names: list[str], n_estimators: int = 200,
                 max_depth: int = 4, learning_rate: float = 0.05, random_state: int = 42):
        self.feature_names = feature_names
        self.model = XGBRegressor(
            n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate,
            min_child_weight=200, subsample=0.8, colsample_bytree=0.8,
            random_state=random_state, n_jobs=-1,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "Tier3GradientBoostSignal":
        valid = X[self.feature_names].notna().all(axis=1) & y.notna()
        self.model.fit(X.loc[valid, self.feature_names], y.loc[valid])
        return self

    def predict(self, X: pd.DataFrame) -> pd.Series:
        valid = X[self.feature_names].notna().all(axis=1)
        pred = pd.Series(np.nan, index=X.index)
        if valid.any():
            pred.loc[valid] = self.model.predict(X.loc[valid, self.feature_names])
        return pred

    def feature_importance(self) -> pd.Series:
        return pd.Series(self.model.feature_importances_, index=self.feature_names).sort_values(ascending=False)
