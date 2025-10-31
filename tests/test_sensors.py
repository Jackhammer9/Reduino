"""Tests for the ultrasonic sensor abstractions."""

from __future__ import annotations

import pytest

from Reduino.Sensors import HCSR04UltrasonicSensor, Ultrasonic, UltrasonicSensor


def test_factory_defaults_to_hcsr04() -> None:
    sensor = Ultrasonic(7, 8)
    assert isinstance(sensor, HCSR04UltrasonicSensor)
    assert isinstance(sensor, UltrasonicSensor)
    assert sensor.trig == 7
    assert sensor.echo == 8
    assert sensor.measure_distance() == 0.0


def test_factory_accepts_model_aliases() -> None:
    sensor = Ultrasonic(1, 2, model="hc_sr04")
    assert isinstance(sensor, HCSR04UltrasonicSensor)


def test_factory_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="Unsupported ultrasonic sensor"):
        Ultrasonic(3, 4, sensor="XYZ")


def test_sensor_validates_pins() -> None:
    with pytest.raises(TypeError):
        Ultrasonic("1", 2)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Ultrasonic(-1, 2)


def test_measure_distance_uses_provider() -> None:
    sensor = Ultrasonic(5, 6, distance_provider=lambda: 42.5)
    assert pytest.approx(sensor.measure_distance(), rel=1e-3) == 42.5


def test_measure_distance_rejects_negative_values() -> None:
    sensor = Ultrasonic(2, 3, distance_provider=lambda: -0.5)
    with pytest.raises(ValueError, match="distance must be non-negative"):
        sensor.measure_distance()


def test_measure_distance_falls_back_to_default() -> None:
    sensor = Ultrasonic(2, 3, default_distance=12.3)
    assert sensor.measure_distance() == 12.3
