"""Behavioural tests for the high-level actuator helpers."""

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
    assert "pinMode(13, OUTPUT);" in cpp