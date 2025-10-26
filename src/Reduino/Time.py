"""Time related helpers mirroring what the transpiled code will perform."""

from __future__ import annotations

from typing import Callable
import time


class Sleep:
    """Represent and optionally execute a millisecond-scale delay."""

    def __init__(
        self,
        duration: int | float,
        *,
        sleep_func: Callable[[float], None] | None = None,
    ) -> None:
        """Create a delay helper.

        Parameters
        ----------
        duration:
            The requested delay in milliseconds.  Negative values are rejected
            because they cannot be represented on the Arduino side either.
        sleep_func:
            Injectable callable used to perform the actual wait when :meth:`wait`
            (or :meth:`__call__`) is invoked.  Defaults to :func:`time.sleep`.
        """

        if duration < 0:
            raise ValueError("duration must be non-negative")

        self.duration_ms = float(duration)
        self._sleep = sleep_func or time.sleep

    @property
    def seconds(self) -> float:
        """Return the configured delay expressed in seconds."""

        return self.duration_ms / 1000.0

    def wait(self) -> None:
        """Block for the configured duration using the injected sleep function."""

        self._sleep(self.seconds)

    def __call__(self) -> None:
        """Calling the instance is equivalent to :meth:`wait`."""

        self.wait()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Sleep(duration_ms={self.duration_ms})"
