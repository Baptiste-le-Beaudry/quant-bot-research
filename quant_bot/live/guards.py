"""Fail-closed safety guards shared by paper and eventual live adapters."""
from __future__ import annotations

from dataclasses import dataclass

import math
import pandas as pd

from quant_bot.config import RISK_PROFILES


class SafetyViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    timestamp: pd.Timestamp
    price: float


def validate_market_snapshot(snapshot: MarketSnapshot, now=None, max_age_seconds: int = 120) -> None:
    timestamp = pd.Timestamp(snapshot.timestamp)
    if timestamp.tzinfo is None:
        raise SafetyViolation("market timestamp must be timezone-aware")
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise SafetyViolation("current timestamp must be timezone-aware")
    if not math.isfinite(snapshot.price) or snapshot.price <= 0:
        raise SafetyViolation("invalid market price")
    age = (now.tz_convert("UTC") - timestamp.tz_convert("UTC")).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise SafetyViolation(f"stale/future market price: age={age:.1f}s")


def assert_live_enabled(profile_name: str) -> None:
    profile = RISK_PROFILES.get(profile_name)
    if profile is None:
        raise SafetyViolation(f"unknown profile {profile_name}")
    if not profile.get("live_enabled", False):
        raise SafetyViolation(f"profile {profile_name} is research/paper-only")


def validate_fill(requested_size: float, filled_size: float, status: str) -> None:
    allowed = {"FILLED", "PARTIALLY_FILLED", "PENDING", "REJECTED"}
    if status not in allowed:
        raise SafetyViolation(f"unknown order status {status}")
    if status == "REJECTED":
        raise SafetyViolation("order rejected")
    if requested_size <= 0 or filled_size < 0 or filled_size > requested_size:
        raise SafetyViolation("invalid requested/filled size")
    if status == "FILLED" and filled_size != requested_size:
        raise SafetyViolation("FILLED order size differs from requested size")
    if status == "PARTIALLY_FILLED" and not 0 < filled_size < requested_size:
        raise SafetyViolation("PARTIALLY_FILLED order requires 0 < fill < request")
    if status == "PENDING" and filled_size != 0:
        raise SafetyViolation("PENDING order cannot report a filled size")
