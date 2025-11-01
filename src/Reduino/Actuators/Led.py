"""High-level actuator primitives used by the transpiler and runtime tests."""

from __future__ import annotations

from collections.abc import Sequence
import sys


def _sleep(*args, **kwargs):
    """Proxy to the package-level ``sleep`` so monkeypatching works."""

    return getattr(sys.modules[__package__], "sleep")(*args, **kwargs)


class Led:
    """Simple in-memory representation of a digital LED pin.

    The class mimics the behaviour the transpiled C++ code will express on the
    Arduino side.  It does not interact with any hardware, making it convenient
    for unit tests and documentation examples executed on a host machine.
    """

    def __init__(self, pin: int = 13) -> None:
        """Create an LED abstraction bound to ``pin``.

        Parameters
        ----------
        pin:
            The Arduino pin number to associate with the LED.  Defaults to the
            built-in LED pin ``13`` on most Arduino boards.
        """

        self.pin = pin
        self.state = False
        self.brightness = 0

    def on(self) -> None:
        """Switch the LED on."""

        self.set_brightness(255)

    def off(self) -> None:
        """Switch the LED off."""

        self.set_brightness(0)

    def get_state(self) -> bool:
        """Return ``True`` when the LED is on."""

        return self.state

    def get_brightness(self) -> int:
        """Return the current brightness level (0-255)."""

        return self.brightness

    def set_brightness(self, value: int) -> None:
        """Update the LED brightness using a PWM style value."""

        if not 0 <= value <= 255:
            raise ValueError("brightness must be between 0 and 255")

        self.brightness = int(value)
        self.state = self.brightness > 0

    def toggle(self) -> None:
        """Flip the LED state from on to off, or vice versa."""

        if self.state:
            self.off()
        else:
            self.on()

    def blink(self, duration_ms: int, times: int = 1) -> None:
        """Blink the LED ``times`` times with ``duration_ms`` delays."""

        if duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if times <= 0:
            raise ValueError("times must be positive")

        for _ in range(times):
            self.on()
            _sleep(duration_ms)
            self.off()
            _sleep(duration_ms)

    def fade_in(self, step: int = 5, delay_ms: int = 10) -> None:
        """Gradually increase brightness towards 255."""

        if step <= 0:
            raise ValueError("step must be positive")
        if delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")

        current = max(0, min(255, int(self.brightness)))
        while current < 255:
            self.set_brightness(current)
            _sleep(delay_ms)
            current = min(255, current + step)
        self.set_brightness(255)

    def fade_out(self, step: int = 5, delay_ms: int = 10) -> None:
        """Gradually decrease brightness towards 0."""

        if step <= 0:
            raise ValueError("step must be positive")
        if delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")

        current = max(0, min(255, int(self.brightness)))
        while current > 0:
            self.set_brightness(current)
            _sleep(delay_ms)
            current = max(0, current - step)
        self.set_brightness(0)

    def flash_pattern(self, pattern: Sequence[int], delay_ms: int = 200) -> None:
        """Execute a sequence of on/off or brightness states."""

        if delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")

        pattern_list = list(pattern)
        for index, entry in enumerate(pattern_list):
            if entry not in (0, 1) and not 0 <= entry <= 255:
                raise ValueError("pattern values must be 0, 1 or within 0-255 brightness range")

            if entry == 0:
                self.off()
            elif entry == 1:
                self.on()
            else:
                self.set_brightness(int(entry))

            if index != len(pattern_list) - 1:
                _sleep(delay_ms)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "Led("
            f"pin={self.pin}, "
            f"state={'on' if self.state else 'off'}, "
            f"brightness={self.brightness}"
            ")"
        )
