import pytest

from Reduino.Sensors import HCSR04UltrasonicSensor, Ultrasonic, UltrasonicSensor


def test_ultrasonic_factory_defaults_to_hcsr04():
    sensor = Ultrasonic(7, 8)
    assert isinstance(sensor, HCSR04UltrasonicSensor)
    assert isinstance(sensor, UltrasonicSensor)
    assert sensor.trig == 7
    assert sensor.echo == 8


def test_ultrasonic_measure_distance_uses_provider():
    sensor = Ultrasonic(5, 6, distance_provider=lambda: 42.5)
    assert pytest.approx(sensor.measure_distance(), rel=1e-3) == 42.5


def test_ultrasonic_factory_rejects_unknown_model():
    with pytest.raises(ValueError):
        Ultrasonic(3, 4, sensor="XYZ")
