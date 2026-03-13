"""
Phase 8 — Attribution Engine

Given an OrderJourney (list of touchpoints) and an order_value,
computes credit distribution under four models:

  - last_click
  - first_click
  - linear
  - time_decay  (credit = e^(-lambda * hours_before_conversion))
"""

import math
from datetime import datetime, timezone
from typing import TypedDict


class Touchpoint(TypedDict):
    session_id: str
    session_start: str | None
    source: str | None
    medium: str | None
    campaign: str | None


class AttributionResult(TypedDict):
    session_id: str
    source: str | None
    medium: str | None
    campaign: str | None
    credit: float  # absolute currency value


# ─── Public API ───────────────────────────────────────────────────────────────

def attribute(
    touchpoints: list[Touchpoint],
    order_value: float,
    conversion_time: datetime,
    model: str = "last_click",
    decay_lambda: float = 0.05,
) -> list[AttributionResult]:
    """
    Compute attribution for a list of touchpoints.

    Args:
        touchpoints: ordered list (oldest first)
        order_value: total order revenue
        conversion_time: when the order was placed
        model: "last_click" | "first_click" | "linear" | "time_decay"
        decay_lambda: rate parameter for time_decay model (per hour)

    Returns:
        List of AttributionResult with credit assigned.
    """
    if not touchpoints:
        return []

    if model == "last_click":
        return _last_click(touchpoints, order_value)
    elif model == "first_click":
        return _first_click(touchpoints, order_value)
    elif model == "linear":
        return _linear(touchpoints, order_value)
    elif model == "time_decay":
        return _time_decay(touchpoints, order_value, conversion_time, decay_lambda)
    else:
        raise ValueError(f"Unknown attribution model: {model}")


def attribute_all_models(
    touchpoints: list[Touchpoint],
    order_value: float,
    conversion_time: datetime,
) -> dict[str, list[AttributionResult]]:
    """Compute all four models at once."""
    return {
        "last_click": _last_click(touchpoints, order_value),
        "first_click": _first_click(touchpoints, order_value),
        "linear": _linear(touchpoints, order_value),
        "time_decay": _time_decay(touchpoints, order_value, conversion_time),
    }


# ─── Models ───────────────────────────────────────────────────────────────────

def _last_click(
    touchpoints: list[Touchpoint], order_value: float
) -> list[AttributionResult]:
    results = [_zero(tp) for tp in touchpoints]
    results[-1]["credit"] = round(order_value, 2)
    return results


def _first_click(
    touchpoints: list[Touchpoint], order_value: float
) -> list[AttributionResult]:
    results = [_zero(tp) for tp in touchpoints]
    results[0]["credit"] = round(order_value, 2)
    return results


def _linear(
    touchpoints: list[Touchpoint], order_value: float
) -> list[AttributionResult]:
    n = len(touchpoints)
    per_touch = round(order_value / n, 2)
    results = []
    total_assigned = 0.0
    for i, tp in enumerate(touchpoints):
        credit = per_touch if i < n - 1 else round(order_value - total_assigned, 2)
        total_assigned += credit
        results.append(_result(tp, credit))
    return results


def _time_decay(
    touchpoints: list[Touchpoint],
    order_value: float,
    conversion_time: datetime,
    decay_lambda: float = 0.05,
) -> list[AttributionResult]:
    """
    credit_i = e^(-lambda * hours_before_conversion)
    Normalized so credits sum to order_value.
    """
    weights = []
    for tp in touchpoints:
        ts = _parse_ts(tp.get("session_start"))
        if ts:
            hours_before = max(0.0, (conversion_time - ts).total_seconds() / 3600)
            w = math.exp(-decay_lambda * hours_before)
        else:
            w = 1.0
        weights.append(w)

    total_weight = sum(weights) or 1.0
    results = []
    total_assigned = 0.0
    for i, (tp, w) in enumerate(zip(touchpoints, weights)):
        if i < len(touchpoints) - 1:
            credit = round(order_value * w / total_weight, 2)
        else:
            credit = round(order_value - total_assigned, 2)
        total_assigned += credit
        results.append(_result(tp, credit))
    return results


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _zero(tp: Touchpoint) -> AttributionResult:
    return _result(tp, 0.0)


def _result(tp: Touchpoint, credit: float) -> AttributionResult:
    return {
        "session_id": tp.get("session_id", ""),
        "source": tp.get("source"),
        "medium": tp.get("medium"),
        "campaign": tp.get("campaign"),
        "credit": credit,
    }


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
