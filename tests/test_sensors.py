"""Tests for the ultrasonic sensor abstractions."""

from __future__ import annotations

import pytest

from Reduino.Sensors import Button, HCSR04UltrasonicSensor, Ultrasonic, UltrasonicSensor


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


def test_button_defaults_to_not_pressed() -> None:
    button = Button(7)
    assert button.is_pressed() == 0


def test_button_reports_state_changes() -> None:
    button = Button(8)
    button.set_pressed(True)
    assert button.is_pressed() == 1
    button.set_pressed(False)
    assert button.is_pressed() == 0


def test_button_invokes_callback_on_press() -> None:
    events = []

    def handler() -> None:
        events.append("clicked")

    button = Button(9, on_click=handler)
    button.set_pressed(False)
    assert button.is_pressed() == 0

    button.set_pressed(True)
    assert button.is_pressed() == 1
    assert events == ["clicked"]

    # Calling while pressed should not trigger the handler again.
    assert button.is_pressed() == 1
    assert events == ["clicked"]

    # Releasing and pressing again invokes the handler once more.
    button.set_pressed(False)
    assert button.is_pressed() == 0
    button.set_pressed(True)
    assert button.is_pressed() == 1
    assert events == ["clicked", "clicked"]


def test_button_validates_pin_type() -> None:
    with pytest.raises(TypeError):
        Button("A0")  # type: ignore[arg-type]
