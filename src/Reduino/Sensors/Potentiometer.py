"""Helpers for working with analogue potentiometer inputs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional


class Potentiometer:
    """In-memory representation of an analogue potentiometer sensor."""

    def __init__(
        self,
        pin: int,
        *,
        value_provider: Optional[Callable[[], int]] = None,
        default_value: int = 0,
    ) -> None:
        if not isinstance(pin, int):
            raise TypeError("pin must be an integer")
        if pin < 0:
            raise ValueError("pin must be non-negative")

        if value_provider is not None and not callable(value_provider):
            raise TypeError("value_provider must be callable")

        self.pin = pin
        self._value_provider = value_provider
        self._value = 0
        self.set_value(default_value)

    def set_value(self, value: int) -> None:
        """Update the simulated analogue reading returned by :meth:`read`."""

        int_value = int(value)
        if int_value < 0 or int_value > 1023:
            raise ValueError("potentiometer value must be between 0 and 1023")
        self._value = int_value

    def read(self) -> int:
        """Return the most recent analogue value (0-1023)."""

        if self._value_provider is None:
            value = self._value
        else:
            value = int(self._value_provider())
        if value < 0 or value > 1023:
            raise ValueError("potentiometer value must be between 0 and 1023")
        return int(value)
