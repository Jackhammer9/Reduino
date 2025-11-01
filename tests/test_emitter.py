"""Unit tests covering emission of Arduino C++ from the AST."""

from __future__ import annotations

from Reduino.transpile.emitter import emit
from Reduino.transpile.parser import parse


def compile_source(source: str) -> str:
    """Helper that parses the DSL ``source`` and returns the generated C++."""

    return emit(parse(source))


def test_emit_generates_setup_and_loop(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Actuators import Led
            from Reduino.Time import Sleep

            led = Led(13)
            led.toggle()
            Sleep(250)
            """
        )
    )

    assert "void setup() {" in cpp
    assert "pinMode(13, OUTPUT);" in cpp
    assert "digitalWrite(13, __state_led ? HIGH : LOW);" in cpp
    assert "delay(250);" in cpp

    loop_section = cpp.split("void loop()", 1)[1]
    assert "// no loop actions" in loop_section or loop_section.strip() == "{\n}\n"


def test_emit_infinite_loop_moves_body_to_loop(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Actuators import Led
            from Reduino.Time import Sleep

            led = Led()
            while True:
                led.toggle()
                Sleep(100)
            """
        )
    )

    loop_section = norm(cpp.split("void loop()", 1)[1])
    assert "digitalWrite(13, __state_led ? HIGH : LOW);" in cpp
    assert "delay(100);" in loop_section


def test_emit_button_generates_polling_loop(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Sensors import Button

            def on_press():
                pass

            btn = Button(pin=2, on_click=on_press)
            """
        )
    )

    text = norm(cpp)
    assert "bool __redu_button_prev_btn = false;" in text
    assert "bool __redu_button_value_btn = false;" in text

    setup_section = cpp.split("void setup() {", 1)[1].split("void loop()", 1)[0]
    assert "pinMode(2, INPUT_PULLUP);" in setup_section
    assert "__redu_button_prev_btn = (digitalRead(2) == HIGH);" in setup_section
    assert "__redu_button_value_btn = __redu_button_prev_btn;" in setup_section

    loop_section = norm(cpp.split("void loop()", 1)[1])
    assert "__redu_button_next_btn = (digitalRead(2) == HIGH);" in loop_section
    assert "on_press();" in loop_section
    assert "__redu_button_value_btn = __redu_button_next_btn;" in loop_section


def test_emit_button_with_while_true_avoids_nested_loop(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Actuators import Led
            from Reduino.Sensors import Button

            led = Led()

            def on_press():
                led.toggle()

            btn = Button(pin=2, on_click=on_press)

            while True:
                led.off()
            """
        )
    )

    text = norm(cpp)
    assert "while (true)" not in text
    loop_section = cpp.split("void loop()", 1)[1]
    assert "digitalWrite(13, LOW);" in loop_section
    assert loop_section.count("on_press();") == 1


def test_emit_potentiometer_reads_analog_value(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Sensors import Potentiometer

            pot = Potentiometer(0)
            value = pot.read()
            """
        )
    )

    setup_section = cpp.split("void setup() {", 1)[1].split("void loop()", 1)[0]
    assert "pinMode(0, INPUT);" in setup_section
    assert "value = analogRead(0);" in cpp


def test_emit_handles_led_and_rgb_led_actions(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Actuators import Led, RGBLed

            led = Led(5)
            led.on()
            led.off()
            led.set_brightness(128)

            rgb = RGBLed(3, 4, 5)
            rgb.set_color(10, 20, 30)
            rgb.fade(255, 0, 0, duration_ms=600, steps=3)
            rgb.blink(0, 0, 255, times=2, delay_ms=125)
            """
        )
    )

    text = norm(cpp)

    assert "pinMode(5, OUTPUT);" in cpp
    assert "digitalWrite(5, HIGH);" in cpp
    assert "digitalWrite(5, LOW);" in cpp
    assert "analogWrite(5, __brightness_led);" in cpp
    assert "bool __state_led = false;" in text

    assert text.count("pinMode(3, OUTPUT);") == 1
    assert "for (int __redu_i = 1; __redu_i <= __redu_steps; ++__redu_i) {" in cpp
    assert "for (int __redu_i = 0; __redu_i < __redu_times; ++__redu_i) {" in cpp
    assert "analogWrite(3, __rgb_red_rgb);" in cpp
    assert "analogWrite(4, __rgb_green_rgb);" in cpp
    assert "analogWrite(5, __rgb_blue_rgb);" in cpp


def test_emit_serial_monitor_and_variables(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Utils import SerialMonitor

            monitor = SerialMonitor(115200)
            counter = 0
            counter += 1
            if counter > 10:
                monitor.write("hi")
            else:
                monitor.write("lo")
            """
        )
    )

    setup_section = cpp.split("void setup() {", 1)[1]
    assert "Serial.begin(115200);" in setup_section
    assert 'Serial.println("hi");' in cpp
    assert 'Serial.println("lo");' in cpp
    assert "int counter = 0;" in cpp
    assert "counter = (counter + 1);" in cpp
    assert "if ((counter > 10))" in cpp


def test_emit_for_range_and_try_except(src, norm) -> None:
    cpp = compile_source(
        src(
            """
            from Reduino.Actuators import Led

            led = Led(9)
            for i in range(3):
                led.toggle()
            try:
                led.on()
            except Exception:
                led.off()
            """
        )
    )

    text = norm(cpp)
    assert "for (int i = 0; i < 3; ++i) {" in cpp
    assert "digitalWrite(9, __state_led ? HIGH : LOW);" in cpp
    assert "try {" in cpp
    assert "catch (Exception &)" in cpp
