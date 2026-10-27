from __future__ import annotations

from dataclasses import dataclass
import pickle
from pathlib import Path

import pandas as pd

from quant_bot.features.build import build_feature_matrix

from .types import FinalizedBar, SignalEvent


@dataclass(frozen=True)
class FrozenSymbolConfig:
    symbol: str
    model: object
    threshold: float
    range_pos_cut: float
    realized_vol_cut: float
    stop_distance: float
    leverage_safe: float
    horizon: int = 10
    max_holding_bars: int = 50
    trailing_activate: float = 0.0063
    trailing_distance: float = 0.0080


@dataclass(frozen=True)
class FrozenStrategyBundle:
    strategy_id: str
    created_at: str
    training_boundary: str
    configs: dict[str, FrozenSymbolConfig]
    live_enabled: bool = False


def save_bundle(bundle: FrozenStrategyBundle, path: str | Path) -> None:
    if bundle.live_enabled:
        raise ValueError("forward Strategy A bundle must remain live-disabled")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        pickle.dump(bundle, handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
    temporary.replace(path)


def load_bundle(path: str | Path) -> FrozenStrategyBundle:
    with Path(path).open("rb") as handle:
        bundle = pickle.load(handle)
    if not isinstance(bundle, FrozenStrategyBundle) or bundle.live_enabled:
        raise ValueError("invalid or live-enabled Strategy A bundle")
    return bundle


class FrozenStrategyASignalEngine:
    """Inference only. No fitting, tuning, or parameter selection at runtime."""

    def __init__(self, bundle: FrozenStrategyBundle):
        if bundle.live_enabled:
            raise ValueError("live-enabled bundle forbidden in paper runner")
        self.bundle = bundle
        self.strategy_id = bundle.strategy_id

    def on_finalized_bar(self, bar: FinalizedBar, history: pd.DataFrame) -> SignalEvent | None:
        config = self.bundle.configs.get(bar.symbol)
        if config is None or history.empty:
            return None
        required = ["open", "high", "low", "close", "volume",
                    "taker_buy_volume", "taker_sell_volume"]
        if any(column not in history for column in required):
            return None
        features = build_feature_matrix(history[required])
        if features.empty:
            return None
        row = features.iloc[[-1]]
        probability = config.model.predict_proba(row).iloc[0]
        if pd.isna(probability):
            return None
        selected = (
            probability > config.threshold
            and float(row.iloc[0]["range_pos_60"]) < config.range_pos_cut
            and float(row.iloc[0]["realized_vol_30"]) > config.realized_vol_cut
        )
        if not selected:
            return None
        return SignalEvent(
            strategy_id=self.strategy_id, symbol=bar.symbol, side="LONG",
            bar_timestamp=bar.open_time, signal_generated_at=bar.processing_timestamp,
            signal_received_at=bar.processing_timestamp, probability=float(probability),
            expected_entry_backtest=bar.close, stop_distance=config.stop_distance,
            leverage_safe=config.leverage_safe, max_holding_bars=config.max_holding_bars,
            trailing_activate=config.trailing_activate,
            trailing_distance=config.trailing_distance,
        )
