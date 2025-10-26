"""High-level actuator primitives used by the transpiler and runtime tests."""

from __future__ import annotations

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

    def on(self) -> None:
        """Switch the LED on."""

        self.state = True

    def off(self) -> None:
        """Switch the LED off."""

        self.state = False

    def get_state(self) -> bool:
        """Return ``True`` when the LED is on."""

        return self.state

    def toggle(self) -> None:
        """Flip the LED state from on to off, or vice versa."""

        self.state = not self.state

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Led(pin={self.pin}, state={'on' if self.state else 'off'})"
