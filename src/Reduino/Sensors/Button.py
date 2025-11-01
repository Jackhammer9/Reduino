from __future__ import annotations

from collections.abc import Callable
from typing import Optional


class Button:
    """In-memory representation of a digital input button."""

    def __init__(
        self,
        pin: int,
        *,
        on_click: Optional[Callable[[], None]] = None,
        state_provider: Optional[Callable[[], bool]] = None,
    ) -> None:
        if not isinstance(pin, int):
            raise TypeError("pin must be an integer")

        if on_click is not None and not callable(on_click):
            raise TypeError("on_click must be callable")

        if state_provider is not None and not callable(state_provider):
            raise TypeError("state_provider must be callable")

        self.pin = pin
        self._on_click = on_click
        self._state_provider = state_provider
        self._pressed = False
        self._was_pressed = False

    def set_pressed(self, pressed: bool) -> None:
        """Update the simulated pressed state used by :meth:`is_pressed`."""

        self._pressed = bool(pressed)

    def is_pressed(self) -> int:
        """Return ``1`` when the button is pressed, ``0`` otherwise."""

        if self._state_provider is None:
            pressed = self._pressed
        else:
            pressed = bool(self._state_provider())

        if pressed and not self._was_pressed and self._on_click is not None:
            self._on_click()

        self._was_pressed = pressed
        return 1 if pressed else 0
