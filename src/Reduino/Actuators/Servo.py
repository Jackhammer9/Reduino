"""High-level abstraction representing a hobby servo."""

from __future__ import annotations


class Servo:
    """In-memory model of a servo actuator.

    The helper mimics a basic positional servo that uses pulse widths between
    ``min_pulse_us`` and ``max_pulse_us`` microseconds to cover the angular range
    from ``min_angle`` to ``max_angle`` degrees.  The defaults match the Arduino
    Servo library (approximately 0-180 degrees mapped to 544-2400 microseconds).
    """

    def __init__(
        self,
        pin: int = 9,
        *,
        min_angle: float = 0.0,
        max_angle: float = 180.0,
        min_pulse_us: float = 544.0,
        max_pulse_us: float = 2400.0,
    ) -> None:
        if min_angle >= max_angle:
            raise ValueError("min_angle must be smaller than max_angle")
        if min_pulse_us >= max_pulse_us:
            raise ValueError("min_pulse_us must be smaller than max_pulse_us")

        self.pin = pin
        self._min_angle = float(min_angle)
        self._max_angle = float(max_angle)
        self._min_pulse = float(min_pulse_us)
        self._max_pulse = float(max_pulse_us)
        self._current_angle = self._min_angle
        self._current_pulse = self._min_pulse

    def _angle_to_pulse(self, angle: float) -> float:
        span_angle = self._max_angle - self._min_angle
        return self._min_pulse + ((angle - self._min_angle) / span_angle) * (
            self._max_pulse - self._min_pulse
        )

    def _pulse_to_angle(self, pulse: float) -> float:
        span_pulse = self._max_pulse - self._min_pulse
        return self._min_angle + ((pulse - self._min_pulse) / span_pulse) * (
            self._max_angle - self._min_angle
        )

    def write(self, angle: float) -> None:
        """Command the servo to ``angle`` degrees."""

        if not self._min_angle <= angle <= self._max_angle:
            raise ValueError("angle must be within the configured bounds")

        self._current_angle = float(angle)
        self._current_pulse = self._angle_to_pulse(self._current_angle)

    def write_us(self, pulse: float) -> None:
        """Command the servo using a pulse width in microseconds."""

        if not self._min_pulse <= pulse <= self._max_pulse:
            raise ValueError("pulse must be within the configured bounds")

        self._current_pulse = float(pulse)
        self._current_angle = self._pulse_to_angle(self._current_pulse)

    def read(self) -> float:
        """Return the last angle requested via :meth:`write` or :meth:`write_us`."""

        return self._current_angle

    def read_us(self) -> float:
        """Return the last pulse width requested."""

        return self._current_pulse

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "Servo("
            f"pin={self.pin}, "
            f"angle={self._current_angle}, "
            f"pulse={self._current_pulse}"
            ")"
        )
