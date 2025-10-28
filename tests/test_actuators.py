"""Behavioural tests for the high-level actuator helpers."""

import pytest

from Reduino.Actuators import Led
from Reduino.transpile.ast import LedDecl
from Reduino.transpile.emitter import emit
from Reduino.transpile.parser import parse


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


def test_led_brightness_control_and_validation():
    led = Led()

    led.set_brightness(128)
    assert led.get_state() is True
    assert led.get_brightness() == 128

    led.set_brightness(0)
    assert led.get_state() is False
    assert led.get_brightness() == 0

    with pytest.raises(ValueError):
        led.set_brightness(300)


def test_led_blink_uses_sleep_and_resets_state(monkeypatch):
    led = Led()
    calls: list[int] = []

    class FakeSleep:
        def __init__(self, duration: int, *, sleep_func=None) -> None:  # pragma: no cover - helper
            calls.append(duration)

        def wait(self) -> None:  # pragma: no cover - helper
            pass

    monkeypatch.setattr("Reduino.Actuators.Sleep", FakeSleep)

    led.blink(duration_ms=50, times=2)

    assert led.get_state() is False
    assert led.get_brightness() == 0
    assert calls == [50, 50, 50, 50]


def test_led_fade_in_and_out(monkeypatch):
    led = Led()
    calls: list[int] = []

    class FakeSleep:
        def __init__(self, duration: int, *, sleep_func=None) -> None:  # pragma: no cover - helper
            calls.append(duration)

        def wait(self) -> None:  # pragma: no cover - helper
            pass

    monkeypatch.setattr("Reduino.Actuators.Sleep", FakeSleep)

    led.fade_in(step=50, delay_ms=5)
    assert led.get_state() is True
    assert led.get_brightness() == 255

    led.fade_out(step=50, delay_ms=5)
    assert led.get_state() is False
    assert led.get_brightness() == 0

    assert calls.count(5) == len(calls)

    with pytest.raises(ValueError):
        led.fade_in(step=0)

    with pytest.raises(ValueError):
        led.fade_out(step=-1)


def test_led_flash_pattern(monkeypatch):
    led = Led()
    calls: list[int] = []

    class FakeSleep:
        def __init__(self, duration: int, *, sleep_func=None) -> None:  # pragma: no cover - helper
            calls.append(duration)

        def wait(self) -> None:  # pragma: no cover - helper
            pass

    monkeypatch.setattr("Reduino.Actuators.Sleep", FakeSleep)

    led.flash_pattern([1, 0, 128, 0], delay_ms=25)
    assert led.get_state() is False
    assert led.get_brightness() == 0
    assert calls == [25, 25, 25]

    with pytest.raises(ValueError):
        led.flash_pattern([300])

def test_led_parser_defaults_builtin_pin(src):
    code = src(
        """
        from Reduino.Actuators import Led

        led = Led()
        """
    )

    prog = parse(code)
    leds = [node for node in prog.setup_body if isinstance(node, LedDecl)]
    assert len(leds) == 1
    assert leds[0].pin == 13


def test_led_emitter_decl_without_args_emits_globals_and_pinmode(norm):
    src_code = """
    from Reduino.Actuators import Led

    led = Led()
    """

    cpp = emit(parse(src_code))
    text = norm(cpp)

    assert "bool __state_led = false;" in text
    assert "int __brightness_led = 0;" in text
    assert "pinMode(13, OUTPUT);" in cpp


def test_led_emitter_pwm_and_state_updates(norm):
    src_code = """
    from Reduino.Actuators import Led

    led = Led(pin=5)
    led.set_brightness(128)
    """

    cpp = emit(parse(src_code))
    text = norm(cpp)

    assert "int __brightness_led = 0;" in text
    assert "analogWrite(5, __brightness_led);" in text
    assert "__state_led = __brightness_led > 0;" in text


def test_led_emitter_blink_generates_loop(norm):
    src_code = """
    from Reduino.Actuators import Led

    led = Led()
    led.blink(duration_ms=200, times=3)
    """

    text = norm(emit(parse(src_code)))

    assert "int __redu_times = 3;" in text
    assert "for (int __redu_i = 0; __redu_i < __redu_times; ++__redu_i) {" in text
    assert text.count("delay(200);") >= 2


def test_led_emitter_fade_and_flash_helpers(norm):
    src_code = """
    from Reduino.Actuators import Led

    led = Led(pin=9)
    led.fade_in(step=5, delay_ms=10)
    led.fade_out(step=5, delay_ms=10)
    led.flash_pattern([1, 0, 64], delay_ms=50)
    """

    cpp = emit(parse(src_code))
    text = norm(cpp)

    assert "analogWrite(9, __brightness_led);" in text
    assert "const int __redu_pattern[] = {1, 0, 64};" in text
    assert "delay(50);" in text
