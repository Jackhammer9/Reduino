"""Unit tests for the Reduino parser."""

import pytest

from Reduino.transpile.ast import (
    BreakStmt,
    ExprStmt,
    ForRangeLoop,
    FunctionDef,
    IfStatement,
    LedDecl,
    ReturnStmt,
    SerialMonitorDecl,
    SerialWrite,
    Sleep,
    TryStatement,
    VarAssign,
    VarDecl,
    WhileLoop,
)
from Reduino.transpile.parser import parse

def test_parser_setup_only(src):
    code = src("""
        from Reduino.Actuators import Led
        from Reduino.Time import Sleep
        # no loop; should go to setup
        led = Led(13)
        led.toggle()
        Sleep(250)
        led.toggle()
    """)
    prog = parse(code)

    assert hasattr(prog, "setup_body")
    assert hasattr(prog, "loop_body")
    assert len(prog.setup_body) > 0
    assert len(prog.loop_body) == 0

def test_parser_while_true_goes_to_loop(src):
    code = src("""
        from Reduino.Actuators import Led
        from Reduino.Time import Sleep
        led = Led()
        while True:
            led.toggle()
            Sleep(500)
    """)
    prog = parse(code)
    assert len(prog.loop_body) > 0

def test_parser_for_range_emits_loop(src):
    code = src("""
        from Reduino.Actuators import Led
        from Reduino.Time import Sleep
        led = Led(8)
        for i in range(3):
            led.toggle()
            Sleep(100)
    """)
    prog = parse(code)
    loops = [node for node in prog.setup_body if isinstance(node, ForRangeLoop)]
    assert len(loops) == 1
    loop = loops[0]
    assert loop.var_name == "i"
    assert loop.count == 3
    assert sum(1 for node in loop.body if node.__class__.__name__ == "LedToggle") == 1
    assert sum(1 for node in loop.body if node.__class__.__name__ == "Sleep") == 1


def test_parser_break_inside_while(src):
    code = src("""
        i = 0
        while i < 5:
            break
    """)

    prog = parse(code)
    loops = [node for node in prog.setup_body if isinstance(node, WhileLoop)]
    assert len(loops) == 1
    loop = loops[0]
    assert any(isinstance(stmt, BreakStmt) for stmt in loop.body)


def test_parser_break_outside_loop_errors(src):
    code = src("""
        break
    """)

    with pytest.raises(ValueError):
        parse(code)


def test_parser_break_in_main_loop_errors(src):
    code = src("""
        from Reduino.Actuators import Led
        led = Led()
        while True:
            break
    """)

    with pytest.raises(ValueError):
        parse(code)

def test_parser_captures_target_port_anywhere(src):
    code = src("""
        from Reduino import target
        target("COM5")
        from Reduino.Actuators import Led
        led = Led()
        while True:
            led.toggle()
        # another target lower should override previous
        target("COM7")
    """)
    prog = parse(code)
    port = getattr(prog, "target_port", None) or getattr(prog, "upload_port", None)
    assert port == "COM7"


def test_parser_resolves_string_concat_to_int(src):
    code = src("""
        from Reduino.Actuators import Led
        from Reduino.Time import Sleep
        a = "3"
        b = "3"
        c = a + b
        led = Led(int(c))
    """)
    prog = parse(code)
    leds = [node for node in prog.setup_body if isinstance(node, LedDecl)]
    assert len(leds) == 1
    assert leds[0].pin == "(c).toInt()"


def test_parser_tuple_assignment_updates_environment(src):
    code = src("""
        from Reduino.Time import Sleep

        a, b = 1, 2
        b, a = a, b
        Sleep(a + b)
    """)

    prog = parse(code)
    sleep_nodes = [node for node in prog.setup_body if isinstance(node, Sleep)]
    assert len(sleep_nodes) == 1
    assert sleep_nodes[0].ms == "(a + b)"


def test_parser_preserves_symbolic_expressions(src):
    code = src("""
        from Reduino.Actuators import Led

        led = Led(pin_base + offset)
    """)

    prog = parse(code)
    led_nodes = [node for node in prog.setup_body if isinstance(node, LedDecl)]
    assert len(led_nodes) == 1
    assert led_nodes[0].pin == "(pin_base + offset)"


def test_parser_serial_monitor_decl_and_write(src):
    code = src(
        """
        from Reduino.Utils import SerialMonitor

        monitor = SerialMonitor(baud_rate=115200)
        monitor.write("hello")
        """
    )

    prog = parse(code)

    serial_nodes = [node for node in prog.setup_body if isinstance(node, SerialMonitorDecl)]
    assert len(serial_nodes) == 1
    assert serial_nodes[0].baud == 115200

    write_nodes = [node for node in prog.setup_body if isinstance(node, SerialWrite)]
    assert len(write_nodes) == 1
    assert write_nodes[0].value == '"hello"'


def test_parser_serial_monitor_accepts_expressions(src):
    code = src(
        """
        from Reduino.Utils import SerialMonitor

        base_rate = 4800
        monitor = SerialMonitor(base_rate * 2)
        monitor.write(base_rate)
        """
    )

    prog = parse(code)

    serial_nodes = [node for node in prog.setup_body if isinstance(node, SerialMonitorDecl)]
    assert len(serial_nodes) == 1
    assert serial_nodes[0].baud == "(base_rate * 2)"

    write_nodes = [node for node in prog.setup_body if isinstance(node, SerialWrite)]
    assert len(write_nodes) == 1
    assert write_nodes[0].value == "base_rate"


def test_parser_allows_led_pin_from_list_index(src):
    code = src("""
        from Reduino.Actuators import Led

        values = [1, 2, 3]
        led = Led(pin=values[2])
    """)

    prog = parse(code)

    led_nodes = [node for node in prog.setup_body if isinstance(node, LedDecl)]
    assert len(led_nodes) == 1
    assert led_nodes[0].pin == "__redu_list_get(values, 2)"


def test_parser_if_elif_else_with_boolean_logic(src):
    code = src("""
        from Reduino.Actuators import Led

        led = Led(7)
        if sensor_value < threshold and not override_flag:
            led.on()
        elif sensor_value == threshold or sensor_value > max_value:
            led.off()
        else:
            led.toggle()
    """)

    prog = parse(code)
    conditionals = [node for node in prog.setup_body if isinstance(node, IfStatement)]
    assert len(conditionals) == 1


def test_parser_try_except_promotes_declarations(src):
    code = src("""
        from Reduino.Actuators import Led

        try:
            level = 1
        except:
            level = 2

        led = Led(level)
    """)

    prog = parse(code)

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert "level" in globals_out
    assert globals_out["level"].expr == "0"

    try_nodes = [node for node in prog.setup_body if isinstance(node, TryStatement)]
    assert len(try_nodes) == 1
    try_stmt = try_nodes[0]
    assert len(try_stmt.try_body) == 1
    assert isinstance(try_stmt.try_body[0], VarAssign)
    assert len(try_stmt.handlers) == 1
    handler = try_stmt.handlers[0]
    assert handler.exception is None
    assert len(handler.body) == 1
    assert isinstance(handler.body[0], VarAssign)


def test_parser_if_preserves_boolean_expression_and_env(src):
    code = src("""
        from Reduino.Actuators import Led

        c = 5
        if 4*2 == 8 and 3*2 == 5:
            c = 7
        led = Led(c)
    """)

    prog = parse(code)
    conditionals = [node for node in prog.setup_body if isinstance(node, IfStatement)]
    assert len(conditionals) == 1
    assert conditionals[0].branches[0].condition == "(((4 * 2) == 8) && ((3 * 2) == 5))"

    leds = [node for node in prog.setup_body if isinstance(node, LedDecl)]
    assert len(leds) == 1
    assert leds[0].pin == "c"


def test_parser_supports_conditional_expression_assignment(src):
    code = src("""
        from Reduino.Actuators import Led

        flag = sensor_ready
        value = 1 if flag else 2
        led = Led(value)
    """)

    prog = parse(code)
    globals_out = {decl.name: decl for decl in prog.global_decls}

    assert globals_out["value"].expr == "0"
    assert globals_out["value"].c_type == "int"

    assigns = [node for node in prog.setup_body if isinstance(node, VarAssign)]
    assert any(node.name == "value" and node.expr == "(flag ? 1 : 2)" for node in assigns)


def test_parser_supports_f_string_expressions(src):
    code = src("""
        name = sensor_id
        message = f"Hello {name}!"
    """)

    prog = parse(code)
    globals_out = {decl.name: decl for decl in prog.global_decls}

    assert "message" in globals_out
    assert globals_out["message"].c_type == "String"
    assert globals_out["message"].expr == '""'


def test_parser_list_features(src):
    code = src("""
        values = [1, 2, 3]
        values.append(4)
        values.remove(2)
        total = values[0]
        other = [i * 2 for i in range(3)]
        values = other
        size = len(other)
    """)

    prog = parse(code)

    assert "list" in prog.helpers

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert "values" in globals_out
    assert globals_out["values"].c_type == "__redu_list<int>"
    assert "__redu_make_list<int>(1, 2, 3)" in globals_out["values"].expr

    append_calls = [
        node.expr
        for node in prog.setup_body
        if isinstance(node, ExprStmt) and "__redu_list_append" in node.expr
    ]
    assert any("__redu_list_append(values, 4)" in expr for expr in append_calls)

    remove_calls = [
        node.expr
        for node in prog.setup_body
        if isinstance(node, ExprStmt) and "__redu_list_remove" in node.expr
    ]
    assert any("__redu_list_remove(values, 2)" in expr for expr in remove_calls)

    assigns = [
        node
        for node in prog.setup_body
        if isinstance(node, VarAssign)
    ]
    assert any(node.name == "total" and "__redu_list_get(values, 0)" in node.expr for node in assigns)
    assert any(
        node.name == "other" and "__redu_list_from_range<int>" in node.expr
        for node in assigns
    )

    assign_calls = [
        node.expr
        for node in prog.setup_body
        if isinstance(node, ExprStmt) and "__redu_list_assign" in node.expr
    ]
    assert any("__redu_list_assign(values, other)" in expr for expr in assign_calls)

    assert any(
        node.name == "size" and "__redu_len(other)" in node.expr
        for node in assigns
    )


def test_parser_list_assignment_size_mismatch_errors(src):
    code = src("""
        values = [1, 2]
        values = [3]
    """)

    with pytest.raises(ValueError):
        parse(code)


def test_parser_list_assignment_type_mismatch_errors(src):
    code = src("""
        values = [1, 2]
        values = ["a", "b"]
    """)

    with pytest.raises(ValueError):
        parse(code)


def test_parser_emits_expression_statements(src):
    code = src("""
        a = 13
        b = 12
        a - b if a > b else b - a
    """)

    prog = parse(code)

    exprs = [node.expr for node in prog.setup_body if isinstance(node, ExprStmt)]

    assert "((a > b) ? (a - b) : (b - a))" in exprs


def test_parser_handles_augmented_assignment(src):
    code = src("""
        from Reduino.Time import Sleep

        counter = 0
        counter += 5
        counter *= 2
        counter //= 3
        Sleep(counter)
    """)

    prog = parse(code)
    assigns = [
        node.expr
        for node in prog.setup_body
        if isinstance(node, VarAssign) and node.name == "counter"
    ]

    assert "(counter + 5)" in assigns
    assert "(counter * 2)" in assigns
    assert "(counter / 3)" in assigns


def test_parser_collects_global_declarations(src):
    code = src("""
        c = 5
        d = c + 2
    """)

    prog = parse(code)
    globals_out = prog.global_decls

    assert len(globals_out) == 2
    assert globals_out[0].name == "c"
    assert globals_out[0].c_type == "int"
    assert globals_out[0].expr == "5"
    assert globals_out[1].name == "d"
    assert globals_out[1].expr == "0"
    assert all(decl.global_scope for decl in globals_out)

    assigns = [node for node in prog.setup_body if isinstance(node, VarAssign)]
    assert any(node.name == "d" and node.expr == "(c + 2)" for node in assigns)


def test_parser_promotes_branch_assignments(src):
    code = src("""
        from Reduino.Actuators import Led

        a = 1
        b = 2

        if a < b:
            c = 3
        else:
            c = 4

        led = Led(c)
    """)

    prog = parse(code)

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert "c" in globals_out
    assert globals_out["c"].expr == "0"

    conditionals = [node for node in prog.setup_body if isinstance(node, IfStatement)]
    assert len(conditionals) == 1
    branch_nodes = conditionals[0].branches[0].body
    else_nodes = conditionals[0].else_body

    assert any(isinstance(node, VarAssign) and node.name == "c" for node in branch_nodes)
    assert any(isinstance(node, VarAssign) and node.name == "c" for node in else_nodes)


def test_parser_handles_while_loops_and_promotes_assignments(src):
    code = src("""
        from Reduino.Actuators import Led

        i = 0
        while i < 3:
            a = 9
            i += 1

        led = Led(a)
    """)

    prog = parse(code)

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert "a" in globals_out
    assert globals_out["a"].expr == "0"

    loops = [node for node in prog.setup_body if isinstance(node, WhileLoop)]
    assert len(loops) == 1
    loop_body = loops[0].body
    assert any(isinstance(node, VarAssign) and node.name == "a" for node in loop_body)
    assert any(isinstance(node, VarAssign) and node.name == "i" for node in loop_body)
def test_parser_emits_builtin_function_calls(src):
    code = src("""
        total = len(readings)
        distance = abs(-5)
        upper = max(1, 4, 2)
        lower = min(upper, 7)
    """)

    prog = parse(code)

    decls = [node for node in prog.global_decls if isinstance(node, VarDecl)]
    expr_map = {decl.name: decl.expr for decl in decls}

    assert expr_map["total"] == "0"
    assert expr_map["distance"] == "abs((-5))"
    assert expr_map["upper"] == "max(max(1, 4), 2)"
    assert expr_map["lower"] == "0"
    assert "len" in prog.helpers

    assigns = [node for node in prog.setup_body if isinstance(node, VarAssign)]
    assert any(
        node.name == "total"
        and node.expr == "static_cast<int>(__redu_len(readings))"
        for node in assigns
    )
    assert any(node.name == "lower" and node.expr == "min(upper, 7)" for node in assigns)


def test_parser_does_not_register_casts_as_helpers(src):
    code = src("""
        a = int("5")
        b = float(3)
        c = bool(1)
        d = str(5)
    """)

    prog = parse(code)

    assert prog.functions == []
    assert prog.helpers == set()


def test_parser_collects_function_definitions(src):
    code = src("""
        def add(a, b):
            total = a + b
            return total

        result = add(2, 3)

        while True:
            result = add(result, 1)
    """)

    prog = parse(code)

    assert len(prog.functions) == 1
    fn = prog.functions[0]
    assert isinstance(fn, FunctionDef)
    assert fn.name == "add"
    assert fn.return_type == "int"
    assert fn.params == [("a", "int"), ("b", "int")]
    assert any(isinstance(node, VarDecl) and node.name == "total" for node in fn.body)
    assert any(isinstance(node, ReturnStmt) and node.expr == "total" for node in fn.body)

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert globals_out["result"].expr == "0"

    assigns = [node for node in prog.setup_body if isinstance(node, VarAssign)]
    assert any(node.name == "result" and node.expr == "add(2, 3)" for node in assigns)

    loop_assigns = [node for node in prog.loop_body if isinstance(node, VarAssign)]
    assert any(node.name == "result" and node.expr == "add(result, 1)" for node in loop_assigns)


def test_parser_infers_function_parameter_types_from_usage(src):
    code = src("""
        def say_hi(person):
            return "Hi, " + person

        greeting = say_hi("Reduino")

        while True:
            greeting = say_hi(greeting)
    """)

    prog = parse(code)

    assert len(prog.functions) == 1
    fn = prog.functions[0]
    assert fn.return_type == "String"
    assert fn.params == [("person", "String")]

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert globals_out["greeting"].c_type == "String"

    assigns = [node for node in prog.setup_body if isinstance(node, VarAssign)]
    assert any(node.name == "greeting" and node.expr == 'say_hi("Reduino")' for node in assigns)

    loop_assigns = [node for node in prog.loop_body if isinstance(node, VarAssign)]
    assert any(node.name == "greeting" and node.expr == "say_hi(greeting)" for node in loop_assigns)


def test_parser_updates_function_types_from_callsite_literals(src):
    code = src("""
        def add(a, b):
            return a + b

        result = add("Hello, ", "World!")
    """)

    prog = parse(code)

    assert len(prog.functions) == 1
    fn = prog.functions[0]
    assert fn.return_type == "String"
    assert fn.params == [("a", "String"), ("b", "String")]

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert globals_out["result"].c_type == "String"

    assigns = [node for node in prog.setup_body if isinstance(node, VarAssign)]
    assert any(node.name == "result" and node.expr == 'add("Hello, ", "World!")' for node in assigns)


def test_parser_creates_function_overloads(src):
    code = src("""
        def add(a, b):
            return a + b

        first = add(1, 2)
        second = add("Hello, ", "World!")
    """)

    prog = parse(code)

    signatures = {
        (fn.return_type, tuple(ptype for _, ptype in fn.params)) for fn in prog.functions
    }

    assert signatures == {
        ("int", ("int", "int")),
        ("String", ("String", "String")),
    }

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert globals_out["first"].c_type == "int"
    assert globals_out["second"].c_type == "String"


def test_parser_supports_void_function_returns(src):
    code = src("""
        def reset_counter():
            counter = 0
            return

        counter = 3

        while True:
            reset_counter()
    """)

    prog = parse(code)

    assert len(prog.functions) == 1
    fn = prog.functions[0]
    assert fn.return_type == "void"
    assert fn.params == []
    assert any(isinstance(node, VarDecl) and node.name == "counter" for node in fn.body)
    assert any(isinstance(node, ReturnStmt) and node.expr is None for node in fn.body)

    globals_out = {decl.name: decl for decl in prog.global_decls}
    assert globals_out["counter"].expr == "3"
