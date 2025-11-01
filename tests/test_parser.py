"""Tests for the Reduino DSL parser."""

from __future__ import annotations

import pytest

from Reduino.transpile.ast import (
    BreakStmt,
    ButtonDecl,
    ButtonPoll,
    ForRangeLoop,
    FunctionDef,
    LedDecl,
    LedOff,
    LedToggle,
    PotentiometerDecl,
    RGBLedBlink,
    RGBLedDecl,
    RGBLedFade,
    RGBLedOff,
    RGBLedOn,
    RGBLedSetColor,
    ServoDecl,
    ServoWrite,
    ServoWriteMicroseconds,
    ReturnStmt,
    SerialMonitorDecl,
    SerialWrite,
    Sleep,
    TryStatement,
    UltrasonicDecl,
    VarAssign,
    WhileLoop,
)
from Reduino.transpile.parser import parse


def _parse(src) -> object:
    return parse(src)


def test_parser_collects_setup_statements(src) -> None:
    code = src(
        """
        from Reduino.Actuators import Led
        from Reduino.Utils import sleep

        led = Led(13)
        led.toggle()
        sleep(250)
        """
    )

    program = _parse(code)
    assert isinstance(program.setup_body[0], LedDecl)
    assert isinstance(program.setup_body[1], LedToggle)
    assert isinstance(program.setup_body[2], Sleep)
    assert program.loop_body == []


def test_parser_promotes_infinite_loop(src) -> None:
    code = src(
        """
        from Reduino.Actuators import Led
        led = Led()
        while True:
            led.toggle()
        """
    )

    program = _parse(code)
    assert program.setup_body
    assert program.loop_body
    assert any(isinstance(stmt, LedToggle) for stmt in program.loop_body)


def test_parser_for_range_creates_loop_node(src) -> None:
    code = src(
        """
        from Reduino.Actuators import Led
        led = Led()
        for i in range(3):
            led.toggle()
        """
    )

    program = _parse(code)
    loops = [node for node in program.setup_body if isinstance(node, ForRangeLoop)]
    assert len(loops) == 1
    loop = loops[0]
    assert loop.var_name == "i"
    assert loop.count == 3
    assert any(isinstance(stmt, LedToggle) for stmt in loop.body)


def test_parser_break_handling(src) -> None:
    code = src(
        """
        i = 0
        while i < 5:
            break
        """
    )

    program = _parse(code)
    while_loops = [node for node in program.setup_body if isinstance(node, WhileLoop)]
    assert len(while_loops) == 1
    loop = while_loops[0]
    assert any(isinstance(stmt, BreakStmt) for stmt in loop.body)

    with pytest.raises(ValueError):
        _parse(src("""break"""))

    with pytest.raises(ValueError):
        _parse(
            src(
                """
                from Reduino.Actuators import Led
                led = Led()
                while True:
                    break
                """
            )
        )


def test_parser_target_detection(src) -> None:
    code = src(
        """
        from Reduino import target

        target("COM5")
        assigned = target("COM6")
        print(target("COM7"))
        """
    )

    program = _parse(code)
    assert program.target_port == "COM7"
    exprs = [node.expr for node in program.setup_body if hasattr(node, "expr")]
    assert all("target" not in expr for expr in exprs)


def test_parser_tuple_assignment_and_var_decl(src) -> None:
    code = src(
        """
        from Reduino.Utils import sleep

        a, b = 1, 2
        b, a = a, b
        sleep(a + b)
        """
    )

    program = _parse(code)
    sleep_nodes = [node for node in program.setup_body if isinstance(node, Sleep)]
    assert len(sleep_nodes) == 1
    assert sleep_nodes[0].ms == "(a + b)"


def test_parser_serial_monitor(src) -> None:
    code = src(
        """
        from Reduino.Communication import SerialMonitor

        monitor = SerialMonitor(115200)
        monitor.write("hello")
        """
    )

    program = _parse(code)
    decls = [node for node in program.setup_body if isinstance(node, SerialMonitorDecl)]
    assert len(decls) == 1
    writes = [node for node in program.setup_body if isinstance(node, SerialWrite)]
    assert len(writes) == 1
    assert writes[0].value == '"hello"'


def test_parser_rgb_led_nodes(src) -> None:
    code = src(
        """
        from Reduino.Actuators import RGBLed

        led = RGBLed(3, 4, 5)
        led.on(1, 2, 3)
        led.set_color(4, 5, 6)
        led.fade(7, 8, 9, duration_ms=100, steps=5)
        led.blink(0, 0, 0, times=2, delay_ms=10)
        led.off()
        """
    )

    program = _parse(code)
    rgb_nodes = [node for node in program.setup_body if node.__class__.__name__.startswith("RGBLed")]
    assert {type(node) for node in rgb_nodes} >= {
        RGBLedDecl,
        RGBLedOn,
        RGBLedSetColor,
        RGBLedFade,
        RGBLedBlink,
        RGBLedOff,
    }


def test_parser_servo_nodes(src) -> None:
    code = src(
        """
        from Reduino.Actuators import Servo

        servo = Servo(9, min_angle=15.0, max_angle=165.0, min_pulse_us=500, max_pulse_us=2400)
        servo.write(90)
        servo.write_us(1500)
        angle = servo.read()
        pulse = servo.read_us()
        """
    )

    program = _parse(code)
    servo_nodes = [node for node in program.setup_body if node.__class__.__name__.startswith("Servo")]
    assert any(isinstance(node, ServoDecl) for node in servo_nodes)
    assert any(isinstance(node, ServoWrite) for node in servo_nodes)
    assert any(isinstance(node, ServoWriteMicroseconds) for node in servo_nodes)

    angle_exprs = [
        getattr(node, "expr", None)
        for node in program.setup_body
        if getattr(node, "name", None) == "angle"
    ]
    pulse_exprs = [
        getattr(node, "expr", None)
        for node in program.setup_body
        if getattr(node, "name", None) == "pulse"
    ]
    assert "__servo_angle_servo" in angle_exprs
    assert "__servo_pulse_servo" in pulse_exprs


def test_parser_try_statement(src) -> None:
    code = src(
        """
        from Reduino.Actuators import Led

        led = Led()
        try:
            led.on()
        except Exception as exc:
            led.off()
        """
    )

    program = _parse(code)
    tries = [node for node in program.setup_body if isinstance(node, TryStatement)]
    assert len(tries) == 1
    try_stmt = tries[0]
    assert try_stmt.handlers[0].target == "exc"
    assert any(isinstance(stmt, LedOff) for stmt in try_stmt.handlers[0].body)


def test_parser_function_definition(src) -> None:
    code = src(
        """
        from Reduino.Actuators import Led

        def blink_twice(pin: int):
            led = Led(pin)
            led.toggle()
            led.toggle()
            return pin
        """
    )

    program = _parse(code)
    assert len(program.functions) == 1
    fn = program.functions[0]
    assert isinstance(fn, FunctionDef)
    assert fn.name == "blink_twice"
    assert fn.return_type == "int"
    assert fn.params == [("pin", "int")]
    assert any(isinstance(stmt, LedToggle) for stmt in fn.body)
    returns = [stmt for stmt in fn.body if isinstance(stmt, ReturnStmt)]
    assert returns and returns[0].expr == "pin"


def test_parser_declares_ultrasonic_sensor(src) -> None:
    code = src(
        """
        from Reduino.Sensors import Ultrasonic

        sensor = Ultrasonic(7, 8)
        distance = sensor.measure_distance()
        """
    )

    program = _parse(code)
    ultrasonic_nodes = [node for node in program.setup_body if isinstance(node, UltrasonicDecl)]
    assert len(ultrasonic_nodes) == 1
    assignments = [node for node in program.setup_body if isinstance(node, VarAssign)]
    assert any(node.name == "distance" for node in assignments)


def test_parser_declares_potentiometer(src) -> None:
    code = src(
        """
        from Reduino.Sensors import Potentiometer

        pot = Potentiometer("A0")
        value = pot.read()
        """
    )

    program = _parse(code)
    pots = [node for node in program.setup_body if isinstance(node, PotentiometerDecl)]
    assert len(pots) == 1
    assignments = [node for node in program.setup_body if isinstance(node, VarAssign)]
    assert any(
        node.name == "value" and "analogRead(A0)" in node.expr for node in assignments
    )


def test_parser_rejects_non_analog_pot_pin(src) -> None:
    code = src(
        """
        from Reduino.Sensors import Potentiometer

        pot = Potentiometer(13)
        """
    )

    with pytest.raises(ValueError, match="analogue pin literal"):
        _parse(code)


def test_parser_records_button_declaration_and_poll(src) -> None:
    code = src(
        """
        from Reduino.Sensors import Button

        def on_press():
            pass

        button = Button(2, on_click=on_press)
        """
    )

    program = _parse(code)

    button_decls = [node for node in program.setup_body if isinstance(node, ButtonDecl)]
    assert len(button_decls) == 1
    assert button_decls[0].name == "button"
    assert button_decls[0].pin == 2
    assert button_decls[0].on_click == "on_press"

    polls = [node for node in program.loop_body if isinstance(node, ButtonPoll)]
    assert [node.name for node in polls] == ["button"]


def test_parser_button_is_pressed_uses_cached_value(src) -> None:
    code = src(
        """
        from Reduino.Sensors import Button

        btn = Button(3)
        pressed = btn.is_pressed()
        """
    )

    program = _parse(code)

    assigns = [node for node in program.setup_body if isinstance(node, VarAssign)]
    assert any(
        node.name == "pressed" and "__redu_button_value_btn" in node.expr
        for node in assigns
    )


def test_parser_promotes_while_true_body_with_button(src) -> None:
    code = src(
        """
        from Reduino.Actuators import Led
        from Reduino.Sensors import Button

        led = Led()
        btn = Button(4)

        while True:
            led.toggle()
        """
    )

    program = _parse(code)

    polls = [node for node in program.loop_body if isinstance(node, ButtonPoll)]
    assert polls and polls[0].name == "btn"

    toggle_ops = [node for node in program.loop_body if isinstance(node, LedToggle)]
    assert toggle_ops, "while True body should be emitted into loop()"

    assert not any(
        isinstance(node, WhileLoop) for node in program.setup_body
    ), "while True should not remain as a literal loop in setup()"
