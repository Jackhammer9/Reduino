"""Utility helpers for interacting with the Reduino runtime."""

from __future__ import annotations

from typing import Callable
import time

__all__ = ["sleep", "map"]


def sleep(
    duration: int | float,
    *,
    sleep_func: Callable[[float], None] | None = None,
) -> None:
    """Block for ``duration`` milliseconds using ``sleep_func``."""

    if duration < 0:
        raise ValueError("duration must be non-negative")

    milliseconds = float(duration)
    seconds = milliseconds / 1000.0
    sleeper = sleep_func or time.sleep
    sleeper(seconds)


def map(value: float, from_low: float, from_high: float, to_low: float, to_high: float) -> float:
    """Linearly map ``value`` from one range to another."""

    if from_low == from_high:
        raise ValueError("from_low and from_high must be different")

    ratio = (value - from_low) / (from_high - from_low)
    return to_low + ratio * (to_high - to_low)
