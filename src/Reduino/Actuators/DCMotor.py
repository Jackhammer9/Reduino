"""In-memory representation of a dual-H-bridge controlled DC motor."""

from __future__ import annotations

from typing import Tuple

import sys


def _sleep(*args, **kwargs):  # pragma: no cover - proxy helper
    """Proxy to the package level ``sleep`` for easier monkeypatching."""

    return getattr(sys.modules[__package__], "sleep")(*args, **kwargs)


class DCMotor:
    """High-level abstraction representing a bidirectional DC motor."""

    _RAMP_STEPS = 20

    def __init__(self, in1: int, in2: int, enable: int) -> None:
        if not all(isinstance(pin, int) for pin in (in1, in2, enable)):
            raise TypeError("motor pins must be integers")
        if len({in1, in2, enable}) != 3:
            raise ValueError("motor pins must be unique")

        self.pins: Tuple[int, int, int] = (in1, in2, enable)
        self._speed = 0.0
        self._inverted = False
        self._mode = "coast"
        self._applied_speed = 0.0

    @staticmethod
    def _clamp_speed(value: float) -> float:
        try:
            speed = float(value)
        except (TypeError, ValueError) as exc:
            raise TypeError("speed must be a number") from exc
        if speed > 1.0:
            return 1.0
        if speed < -1.0:
            return -1.0
        return speed

    def get_speed(self) -> float:
        """Return the last requested (pre-inversion) speed."""

        return self._speed

    def get_applied_speed(self) -> float:
        """Return the effective speed after applying inversion."""

        return self._applied_speed

    def is_inverted(self) -> bool:
        """Return ``True`` if the motor direction is inverted."""

        return self._inverted

    def get_mode(self) -> str:
        """Return the current drive mode (``drive``, ``coast`` or ``brake``)."""

        return self._mode

    def set_speed(self, value: float) -> None:
        """Drive the motor using ``value`` in the ``[-1.0, 1.0]`` range."""

        speed = self._clamp_speed(value)
        self._speed = speed
        self._apply_speed(speed)

    def _apply_speed(self, speed: float) -> None:
        effective = -speed if self._inverted else speed
        if effective == 0.0:
            self._mode = "coast"
        else:
            self._mode = "drive"
        self._applied_speed = effective

    def backward(self, speed: float = 1.0) -> None:
        """Shortcut for commanding a negative (reverse) speed."""

        magnitude = abs(self._clamp_speed(speed))
        self.set_speed(-magnitude)

    def stop(self) -> None:
        """Actively brake the motor by shorting the terminals."""

        self._speed = 0.0
        self._applied_speed = 0.0
        self._mode = "brake"

    def coast(self) -> None:
        """Let the motor spin down freely."""

        self._speed = 0.0
        self._applied_speed = 0.0
        self._mode = "coast"

    def invert(self) -> None:
        """Toggle the direction of rotation for subsequent commands."""

        self._inverted = not self._inverted
        self._apply_speed(self._speed)

    def ramp(self, target_speed: float, duration_ms: float) -> None:
        """Linearly ramp from the current speed to ``target_speed``."""

        if duration_ms < 0:
            raise ValueError("duration must be non-negative")

        target = self._clamp_speed(target_speed)
        start = self._speed
        if self._RAMP_STEPS <= 0:
            self.set_speed(target)
            return

        step_value = (target - start) / self._RAMP_STEPS
        delay_ms = duration_ms / self._RAMP_STEPS if self._RAMP_STEPS else 0
        for step in range(1, self._RAMP_STEPS + 1):
            self.set_speed(start + step_value * step)
            if delay_ms > 0:
                _sleep(delay_ms)

    def run_for(self, duration_ms: float, speed: float) -> None:
        """Drive the motor at ``speed`` for ``duration_ms`` milliseconds."""

        if duration_ms < 0:
            raise ValueError("duration must be non-negative")

        self.set_speed(speed)
        _sleep(duration_ms)
        self.stop()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "DCMotor("
            f"pins={self.pins}, "
            f"speed={self._speed:.2f}, "
            f"applied={self._applied_speed:.2f}, "
            f"mode={self._mode}, "
            f"inverted={self._inverted}" ")"
        )
