from __future__ import annotations

from collections.abc import Callable
from typing import Optional


class UltrasonicSensor:
    """Base abstraction for ultrasonic distance sensors.

    The class stores the trigger/echo pin mapping and provides a
    pluggable ``distance_provider`` callable to make unit tests predictable
    without requiring hardware access.
    """

    model: str = "generic"

    def __init__(
        self,
        trig: int,
        echo: int,
        *,
        distance_provider: Optional[Callable[[], float]] = None,
        default_distance: float = 0.0,
    ) -> None:
        if not isinstance(trig, int) or not isinstance(echo, int):
            raise TypeError("trig and echo pins must be integers")
        if trig < 0 or echo < 0:
            raise ValueError("trig and echo pins must be non-negative")

        self.trig = trig
        self.echo = echo
        self._distance_provider = distance_provider
        self._default_distance = float(default_distance)

    def measure_distance(self) -> float:
        """Return the most recently simulated distance in centimetres."""

        if self._distance_provider is None:
            distance = self._default_distance
        else:
            distance = float(self._distance_provider())
        if distance < 0:
            raise ValueError("distance must be non-negative")
        return float(distance)


class HCSR04UltrasonicSensor(UltrasonicSensor):
    """Concrete implementation for the popular HC-SR04 sensor."""

    model = "HC-SR04"

    def __init__(
        self,
        trig: int,
        echo: int,
        *,
        distance_provider: Optional[Callable[[], float]] = None,
        default_distance: float = 0.0,
    ) -> None:
        super().__init__(
            trig,
            echo,
            distance_provider=distance_provider,
            default_distance=default_distance,
        )


_SENSOR_MODELS = {"HC-SR04": HCSR04UltrasonicSensor}


def Ultrasonic(
    trig: int,
    echo: int,
    *,
    sensor: Optional[str] = None,
    model: Optional[str] = None,
    distance_provider: Optional[Callable[[], float]] = None,
    default_distance: float = 0.0,
) -> UltrasonicSensor:
    """Factory that instantiates an ultrasonic sensor helper.

    Parameters
    ----------
    trig, echo:
        Pin numbers used to drive the HC-SR04 module.
    sensor, model:
        Optional selector for the sensor type. ``"HC-SR04"`` is the only
        supported value at the moment and is chosen automatically when left
        unspecified. ``model`` is accepted as an alias for ``sensor`` for
        future compatibility.
    distance_provider:
        Optional callable returning a simulated distance in centimetres.
    default_distance:
        Fallback distance (in centimetres) used when no provider is supplied.
    """

    selected = sensor if sensor is not None else model
    if selected is None:
        selected = "HC-SR04"
    canonical = selected.strip().upper().replace("_", "-")
    if canonical not in _SENSOR_MODELS:
        raise ValueError(f"Unsupported ultrasonic sensor '{selected}'")
    sensor_cls = _SENSOR_MODELS[canonical]
    return sensor_cls(
        trig,
        echo,
        distance_provider=distance_provider,
        default_distance=default_distance,
    )
