"""RGB LED actuator abstraction used by the runtime helpers."""

from __future__ import annotations

from collections.abc import Iterable
import sys


def _sleep(*args, **kwargs):
    """Proxy to the package-level ``sleep`` so monkeypatching works."""

    return getattr(sys.modules[__package__], "sleep")(*args, **kwargs)


class RGBLed:
    """Simple in-memory representation of an RGB LED.

    The helper mirrors how the transpiled C++ code would operate on the Arduino
    side while remaining fully deterministic for unit tests running on a host
    machine.
    """

    def __init__(self, red_pin: int, green_pin: int, blue_pin: int) -> None:
        """Create an RGB LED bound to three PWM capable pins."""

        self._pins = (
            self._validate_pin(red_pin, "red"),
            self._validate_pin(green_pin, "green"),
            self._validate_pin(blue_pin, "blue"),
        )
        self._color = (0, 0, 0)
        self._state = False

    @staticmethod
    def _validate_pin(pin: int, name: str) -> int:
        if not isinstance(pin, int):
            raise TypeError(f"{name} pin must be an integer")
        if pin < 0:
            raise ValueError(f"{name} pin must be non-negative")
        return pin

    @staticmethod
    def _validate_component(value: int, name: str) -> int:
        if not isinstance(value, int):
            raise TypeError(f"{name} component must be an integer")
        if not 0 <= value <= 255:
            raise ValueError(f"{name} component must be between 0 and 255")
        return int(value)

    @property
    def pins(self) -> tuple[int, int, int]:
        """Return the configured pins in ``(red, green, blue)`` order."""

        return self._pins

    def get_color(self) -> tuple[int, int, int]:
        """Return the current ``(red, green, blue)`` intensity tuple."""

        return self._color

    def get_state(self) -> bool:
        """Return ``True`` when any of the colour channels is on."""

        return self._state

    def _update_state(self, color: Iterable[int]) -> None:
        self._state = any(component > 0 for component in color)

    def set_color(self, red: int, green: int, blue: int) -> None:
        """Set the RGB LED to a specific colour."""

        colour = (
            self._validate_component(red, "red"),
            self._validate_component(green, "green"),
            self._validate_component(blue, "blue"),
        )
        self._color = colour
        self._update_state(colour)

    def on(self, red: int = 255, green: int = 255, blue: int = 255) -> None:
        """Switch the LED on using the provided colour intensities."""

        self.set_color(red, green, blue)

    def off(self) -> None:
        """Switch the LED off."""

        self.set_color(0, 0, 0)

    def fade(
        self,
        red: int,
        green: int,
        blue: int,
        duration_ms: int | float = 1000,
        steps: int = 50,
    ) -> None:
        """Gradually transition to the provided colour over ``duration_ms``."""

        if duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if steps <= 0:
            raise ValueError("steps must be positive")

        target = (
            self._validate_component(red, "red"),
            self._validate_component(green, "green"),
            self._validate_component(blue, "blue"),
        )

        if duration_ms == 0 or self._color == target:
            self.set_color(*target)
            return

        start = self._color
        step_delay = float(duration_ms) / steps
        for index in range(1, steps + 1):
            interpolated = []
            for current, goal in zip(start, target):
                delta = goal - current
                value = current + (delta * index) / steps
                interpolated.append(int(round(value)))
            self.set_color(*interpolated)
            if index != steps:
                _sleep(step_delay)

    def blink(
        self,
        red: int,
        green: int,
        blue: int,
        times: int = 1,
        delay_ms: int | float = 200,
    ) -> None:
        """Blink the LED ``times`` times using the provided colour."""

        if times <= 0:
            raise ValueError("times must be positive")
        if delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")

        colour = (
            self._validate_component(red, "red"),
            self._validate_component(green, "green"),
            self._validate_component(blue, "blue"),
        )

        original = self._color
        for _ in range(times):
            self.set_color(*colour)
            _sleep(delay_ms)
            self.off()
            _sleep(delay_ms)
        self.set_color(*original)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"RGBLed(pins={self._pins}, "
            f"state={'on' if self._state else 'off'}, "
            f"color={self._color})"
        )
