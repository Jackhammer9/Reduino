"""Helpers for working with analogue potentiometer inputs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional


class Potentiometer:
    """In-memory representation of an analogue potentiometer sensor."""

    def __init__(
        self,
        pin: str,
        *,
        value_provider: Optional[Callable[[], int]] = None,
    ) -> None:
        if not isinstance(pin, str):
            raise TypeError("pin must be a string")
        stripped = pin.strip()
        if not stripped or stripped[0] != "A" or not stripped[1:].isdigit():
            raise ValueError("pin must be an analogue pin like 'A0'")

        if value_provider is not None and not callable(value_provider):
            raise TypeError("value_provider must be callable")

        self.pin = stripped
        self._value_provider = value_provider

    def read(self) -> int:
        """Return the most recent analogue value (0-1023)."""

        if self._value_provider is None:
            value = 0
        else:
            value = int(self._value_provider())
        if value < 0 or value > 1023:
            raise ValueError("potentiometer value must be between 0 and 1023")
        return int(value)
