"""Unit tests covering emission of Arduino C++ from the AST."""

from textwrap import dedent

from Reduino.transpile.emitter import emit
from Reduino.transpile.parser import parse

def test_emit_setup_only_generates_setup(norm):
    src = """
    from Reduino.Actuators import Led
    from Reduino.Time import Sleep
    led = Led(13)
    led.toggle()
    Sleep(250)
    led.toggle()
    """
    cpp = emit(parse(src))
    assert "void setup() {" in cpp
    assert "void loop() {" in cpp
    assert "// no loop actions" in cpp or "void loop() {\n}\n" in cpp
    assert "pinMode(13, OUTPUT);" in cpp
    assert "delay(250);" in cpp

def test_emit_infinite_loop_goes_to_loop(norm):
    src = """
    from Reduino.Actuators import Led
    from Reduino.Time import Sleep
    led = Led()
    while True:
        led.toggle()
        Sleep(500)
    """
    cpp = emit(parse(src))
    assert "void loop() {" in cpp
    assert "delay(500);" in cpp


def test_emit_led_actions_affect_output(norm):
    src = """
    from Reduino.Actuators import Led
    from Reduino.Time import Sleep

    led = Led(5)
    led.on()
    led.off()
    led.toggle()
    Sleep(125)
    """

    cpp = emit(parse(src))
    text = norm(cpp)
    assert "pinMode(5, OUTPUT);" in cpp
    assert "digitalWrite(5, HIGH);" in cpp
    assert "digitalWrite(5, LOW);" in cpp
    assert "digitalWrite(5, __state_led ? HIGH : LOW);" in cpp
    assert "delay(125);" in cpp
    assert "bool __state_led = false;" in text


def test_emit_if_elif_else_and_boolean_ops(norm):
    src = """
    from Reduino.Actuators import Led

    led = Led(6)
    if sensor_value < threshold and not override_flag:
        led.on()
    elif sensor_value == threshold or sensor_value > max_value:
        led.off()
    else:
        led.toggle()
    """

    cpp = norm(emit(parse(src)))
    assert "if (((sensor_value < threshold) && (!override_flag))) {" in cpp
    assert "else if (((sensor_value == threshold) || (sensor_value > max_value))) {" in cpp
    assert "else {" in cpp
    assert "digitalWrite(6, HIGH);" in cpp
    assert "digitalWrite(6, LOW);" in cpp
    assert "digitalWrite(6, __state_led ? HIGH : LOW);" in cpp


def test_emit_declares_globals_and_uses_expressions(norm):
    src = """
    from Reduino.Actuators import Led

    c = 5
    d = c + 2
    led = Led(d)
    """

    cpp = emit(parse(src))
    text = norm(cpp)

    assert "int c = 5;" in cpp
    assert "int d = 0;" in cpp
    assert "pinMode(d, OUTPUT);" in cpp
    assert "digitalWrite(d, HIGH);" not in cpp  # no actions emitted
    assert "bool __state_led = false;" in text

    setup_section = cpp.split("void setup() {", 1)[1]
    assert "d = (c + 2);" in setup_section


def test_led_pinmode_follows_conditional_assignment(norm):
    src = """
    from Reduino.Actuators import Led

    a = 1
    b = 2

    if a < b:
        c = 7
    else:
        c = 9

    led = Led(c)
    """

    cpp = emit(parse(src))
    setup_section = cpp.split("void setup() {", 1)[1]

    assert "int c = 0;" in cpp
    assert setup_section.index("if ((a < b)) {") < setup_section.index("pinMode(c, OUTPUT);")
    assert "c = 7;" in setup_section
    assert "c = 9;" in setup_section


def test_emit_serial_monitor(norm):
    src = """
    from Reduino.Utils import SerialMonitor

    monitor = SerialMonitor(115200)
    monitor.write("hi")
    """

    cpp = emit(parse(src))
    text = norm(cpp)

    assert "Serial.begin(115200);" in cpp
    assert 'Serial.println("hi");' in cpp
    # ensure helper lands in setup body
    setup_section = text.split("void loop()", 1)[0]
    assert "Serial.begin(115200);" in setup_section


def test_emit_ultrasonic_measurement(norm):
    src = """
    from Reduino.Sensors import Ultrasonic

    sensor = Ultrasonic(12, 11)
    distance = sensor.measure_distance()
    """

    cpp = emit(parse(src))
    text = norm(cpp)

    assert "pinMode(12, OUTPUT);" in cpp
    assert "pinMode(11, INPUT);" in cpp
    assert "float __redu_ultrasonic_measure_sensor()" in cpp
    assert "distance = __redu_ultrasonic_measure_sensor();" in text
    assert "static unsigned long __redu_last_trigger_ms_sensor = 0UL;" in cpp
    assert "static float __redu_last_distance_sensor = 400.0f;" in cpp
    assert "static bool __redu_has_distance_sensor = false;" in cpp
    assert "for (unsigned int __redu_attempt_sensor = 0U;" in cpp
    assert "delay(__redu_min_interval_ms_sensor - __redu_elapsed_ms_sensor);" in cpp
    assert "pulseIn(11, HIGH, 30000UL);" in cpp
    assert "__redu_has_distance_sensor = true;" in cpp
    assert "return 400.0f;" in cpp
    assert "delayMicroseconds(10);" in cpp
def test_emit_includes_len_helper_and_call(norm):
    src = """
    total = len(readings)
    """

    cpp = emit(parse(src))
    text = norm(cpp)

    assert "#include <cstring>" in cpp
    assert "static_cast<int>(__redu_len(readings))" in cpp
    assert "__redu_len" in text


def test_emit_while_loop_emits_structure(norm):
    src = """
    from Reduino.Actuators import Led

    i = 0
    while i < 3:
        a = 9
        i += 1

    led = Led(a)
    """

    cpp = norm(emit(parse(dedent(src))))

    assert "int a = 0;" in cpp
    assert "while ((i < 3)) {" in cpp
    assert "a = 9;" in cpp


def test_emit_try_except(norm):
    src = """
    from Reduino.Actuators import Led

    try:
        level = 1
    except:
        level = 2

    led = Led(level)
    """

    cpp = norm(emit(parse(src)))

    assert "int level = 0;" in cpp
    assert "try {" in cpp
    assert "level = 1;" in cpp
    assert "catch (...) {" in cpp
    assert "level = 2;" in cpp


def test_emit_function_with_string_parameter(norm):
    src = """
    def say_hi(person):
        return "Hi, " + person

    greeting = say_hi("Reduino")

    while True:
        greeting = say_hi(greeting)
    """

    cpp = emit(parse(dedent(src)))
    text = norm(cpp)

    assert "String say_hi(String person) {" in text
    assert 'return ("Hi, " + person);' in cpp
    assert 'String greeting = "";' in cpp
    assert 'greeting = say_hi("Reduino");' in cpp
    assert "greeting = say_hi(greeting);" in cpp


def test_emit_list_support(norm):
    src = """
    values = [1, 2, 3]
    values.append(4)
    values.remove(2)
    total = values[0]
    other = [i * 2 for i in range(3)]
    values = other
    size = len(other)
    """

    cpp = norm(emit(parse(dedent(src))))

    assert "__redu_make_list<int>(1, 2, 3)" in cpp
    assert "__redu_list_append(values, 4);" in cpp
    assert "__redu_list_remove(values, 2);" in cpp
    assert "__redu_list_get(values, 0)" in cpp
    assert "__redu_list_from_range<int>(0, 3, 1, [&](int i) { return (i * 2); })" in cpp
    assert "__redu_list_assign(values, other);" in cpp
    assert "static_cast<int>(__redu_len(other))" in cpp


def test_emit_led_pin_from_list_index(norm):
    src = """
    from Reduino.Actuators import Led

    values = [1, 2, 3]
    led = Led(pin=values[1])
    """

    cpp = norm(emit(parse(dedent(src))))

    assert "__redu_make_list<int>(1, 2, 3)" in cpp
    assert "bool __state_led = false;" in cpp
    assert "pinMode(__redu_list_get(values, 1), OUTPUT);" in cpp


def test_emit_function_parameter_types_from_callsite_literals(norm):
    src = """
    def add(a, b):
        return a + b

    result = add("Hello, ", "World!")
    """

    cpp = emit(parse(dedent(src)))
    text = norm(cpp)

    assert "String add(String a, String b) {" in text
    assert 'return (a + b);' in cpp
    assert 'String result = "";' in cpp
    assert 'result = add("Hello, ", "World!");' in cpp


def test_emit_function_overloads(norm):
    src = """
    def add(a, b):
        return a + b

    total = add(1, 2)
    message = add("Hi, ", "there")
    """

    cpp = emit(parse(dedent(src)))
    text = norm(cpp)

    assert "int add(int a, int b) {" in text
    assert "String add(String a, String b) {" in text
    assert "int total = 0;" in cpp
    assert 'String message = "";' in cpp
    assert "total = add(1, 2);" in cpp
    assert 'message = add("Hi, ", "there");' in cpp


def test_emit_builtin_casts(norm):
    src = """
    from Reduino.Actuators import Led

    a = int("5")
    b = str(5)

    led = Led(a)

    while True:
        led.toggle()
    """

    cpp = emit(parse(dedent(src)))

    assert 'int a = String("5").toInt();' in cpp
    assert "String b = String(5);" in cpp
    assert "str(5)" not in cpp


def test_emit_builtin_int_assignment(norm):
    src = """
    from Reduino.Actuators import Led

    a = 13
    a = int("5")

    led = Led(a)
    """

    cpp = emit(parse(dedent(src)))
    setup_section = cpp.split("void setup() {", 1)[1].split("}\n\nvoid loop()", 1)[0]

    assert "int a = 13;" in cpp
    assert 'a = String("5").toInt();' in setup_section


def test_emit_builtin_float_from_string(norm):
    src = """
    value = float("3.14")
    """

    cpp = emit(parse(dedent(src)))

    assert 'float value = String("3.14").toFloat();' in cpp


def test_global_assignments_execute_in_source_order(norm):
    src = """
    from Reduino.Actuators import Led

    a = 13
    b = 12

    a - b if a > b else b - a

    c = f"Hello, Reduino! {a+b}"

    a -= 2
    b += 2

    led = Led(a)
    """

    cpp = emit(parse(dedent(src)))
    text = norm(cpp)

    assert "int a = 13;" in cpp
    assert "int b = 12;" in cpp
    assert "String c = \"\";" in cpp
    assert "bool __state_led = false;" in text

    setup_section = cpp.split("void setup() {", 1)[1].split("}\n\nvoid loop()", 1)[0]

    first_a = "a = 13;"
    first_b = "b = 12;"
    diff_expr = "((a > b) ? (a - b) : (b - a));"
    c_assign = "c = (String(\"Hello, Reduino! \") + String((a + b)));"
    sub_a = "a = (a - 2);"
    add_b = "b = (b + 2);"

    assert first_a not in setup_section
    assert first_b not in setup_section
    assert setup_section.index(diff_expr) >= 0
    assert setup_section.index(c_assign) > setup_section.index(diff_expr)
    assert setup_section.index(sub_a) > setup_section.index(c_assign)
    assert setup_section.index(add_b) > setup_section.index(sub_a)
    assert setup_section.index("pinMode(a, OUTPUT);") > setup_section.index(add_b)


def test_emit_break_within_while(norm):
    src = """
    from Reduino.Actuators import Led

    count = 0
    while count < 5:
        count += 1
        if count > 2:
            break

    led = Led(count)
    """

    cpp = emit(parse(dedent(src)))
    while_section = cpp.split("while ((count < 5)) {", 1)[1].split("}\n", 1)[0]
    assert "break;" in while_section


def test_emit_for_loop_with_break(norm):
    src = """
    from Reduino.Actuators import Led

    led = Led(8)
    for i in range(4):
        if i == 2:
            break
        led.toggle()
    """

    cpp = emit(parse(dedent(src)))
    assert "for (int i = 0; i < 4; ++i) {" in cpp
    loop_section = cpp.split("for (int i = 0; i < 4; ++i) {", 1)[1].split("}\n", 1)[0]
    assert "if ((i == 2)) {" in loop_section
    assert "break;" in loop_section
    assert "digitalWrite(8, __state_led ? HIGH : LOW);" in cpp


def test_emit_includes_function_definitions(norm):
    src = """
    def multiply(a, b):
        product = a * b
        return product

    factor = multiply(2, 3)

    while True:
        factor = multiply(factor, 2)
    """

    cpp = emit(parse(dedent(src)))

    assert "int multiply(int a, int b) {" in cpp
    assert "int product = (a * b);" in cpp
    assert "return product;" in cpp
    assert cpp.index("int multiply(int a, int b) {") < cpp.index("void setup() {")

    setup_section = cpp.split("void setup() {", 1)[1].split("}\n\nvoid loop()", 1)[0]
    assert "factor = multiply(2, 3);" in setup_section

    loop_section = cpp.split("void loop() {", 1)[1]
    assert "factor = multiply(factor, 2);" in loop_section


def test_emit_void_function(norm):
    src = """
    def reset(value):
        temp = value + 1
        return

    counter = 5

    while True:
        reset(counter)
    """

    cpp = emit(parse(dedent(src)))

    assert "void reset(int value) {" in cpp
    assert "int temp = (value + 1);" in cpp
    assert "return;" in cpp.split("void reset(int value) {", 1)[1].split("}\n", 1)[0]
    assert cpp.index("void reset(int value) {") < cpp.index("void setup() {")
