"""Behavioural tests for the high-level actuator helpers."""

from Reduino.Actuators import Led


def test_led_initial_state_and_pin_defaults():
    led = Led()
    assert led.pin == 13
    assert led.get_state() is False


def test_led_state_transitions():
    led = Led(pin=7)

    led.on()
    assert led.get_state() is True

    led.off()
    assert led.get_state() is False

    led.toggle()
    assert led.get_state() is True

    led.toggle()
    assert led.get_state() is False
