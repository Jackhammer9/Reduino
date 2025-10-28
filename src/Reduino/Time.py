"""Time related helpers mirroring what the transpiled code will perform."""

from __future__ import annotations

from typing import Callable
import time


def Sleep(
    duration: int | float,
    *,
    sleep_func: Callable[[float], None] | None = None,
) -> None:
    """Block for ``duration`` milliseconds using ``sleep_func``.

    Parameters
    ----------
    duration:
        The requested delay in milliseconds.  Negative values are rejected
        because they cannot be represented on the Arduino side either.
    sleep_func:
        Injectable callable used to perform the actual wait.  Defaults to
        :func:`time.sleep`.
    """

    if duration < 0:
        raise ValueError("duration must be non-negative")

    milliseconds = float(duration)
    seconds = milliseconds / 1000.0
    sleeper = sleep_func or time.sleep
    sleeper(seconds)
