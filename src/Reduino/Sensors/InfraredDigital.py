"""Structured placeholder helper for digital infrared sensors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional


class InfraredDigital:
    """Placeholder abstraction for digital infrared obstacle sensors.

    This helper is intentionally lightweight for runtime simulation while the
    real Arduino behavior is produced by the DSL transpiler.
    """

    def __init__(
        self,
        pin: int,
        *,
        state_provider: Optional[Callable[[], bool]] = None,
        default_state: bool = False,
    ) -> None:
        if not isinstance(pin, int):
            raise TypeError("pin must be an integer")
        if pin < 0:
            raise ValueError("pin must be non-negative")
        if state_provider is not None and not callable(state_provider):
            raise TypeError("state_provider must be callable")

        self.pin = pin
        self._state_provider = state_provider
        self._default_state = bool(default_state)

    def read(self) -> int:
        """Return ``1`` when an object is detected, ``0`` otherwise."""

        if self._state_provider is None:
            detected = self._default_state
        else:
            detected = bool(self._state_provider())
        return 1 if detected else 0
