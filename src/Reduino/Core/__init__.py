"""Host-side stubs for the low-level Reduino Core helpers.

These helpers provide a minimal in-memory simulation of the Arduino
``pinMode``/``digitalWrite``/``analogWrite`` family so that importing
``Reduino.Core`` succeeds when running documentation examples or unit tests
on a host machine.  The transpiler recognises these names and replaces them
with the corresponding Arduino calls during code generation.
"""

from __future__ import annotations

from typing import Dict, Union

__all__ = [
    "pin_mode",
    "digital_write",
    "analog_write",
    "digital_read",
    "analog_read",
    "INPUT",
    "OUTPUT",
    "INPUT_PULLUP",
    "HIGH",
    "LOW",
]


INPUT = "INPUT"
OUTPUT = "OUTPUT"
INPUT_PULLUP = "INPUT_PULLUP"
HIGH = 1
LOW = 0

_PinKey = Union[int, str]

_pin_modes: Dict[_PinKey, str] = {}
_digital_values: Dict[_PinKey, int] = {}
_analog_values: Dict[_PinKey, int] = {}


def _normalise_pin(pin: _PinKey) -> _PinKey:
    if isinstance(pin, str) and pin.isdigit():
        return int(pin)
    return pin


def pin_mode(pin: _PinKey, mode: str) -> None:
    """Record the configured ``mode`` for ``pin`` in the host simulation."""

    key = _normalise_pin(pin)
    _pin_modes[key] = mode
    if mode == INPUT_PULLUP and key not in _digital_values:
        _digital_values[key] = HIGH


def digital_write(pin: _PinKey, value: Union[int, bool]) -> None:
    """Store the logical ``value`` for ``pin`` in the host simulation."""

    key = _normalise_pin(pin)
    _digital_values[key] = HIGH if bool(value) else LOW


def analog_write(pin: _PinKey, value: Union[int, float]) -> None:
    """Store the PWM ``value`` (0-255) for ``pin`` in the host simulation."""

    key = _normalise_pin(pin)
    scaled = int(round(float(value)))
    _analog_values[key] = max(0, min(255, scaled))


def digital_read(pin: _PinKey) -> int:
    """Return the previously stored logical value for ``pin``."""

    key = _normalise_pin(pin)
    if key in _digital_values:
        return _digital_values[key]
    if _pin_modes.get(key) == INPUT_PULLUP:
        return HIGH
    return LOW


def analog_read(pin: _PinKey) -> int:
    """Return the previously stored analogue value for ``pin``."""

    key = _normalise_pin(pin)
    return _analog_values.get(key, 0)

