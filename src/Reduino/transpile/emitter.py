"""Translate Reduino AST nodes into Arduino-flavoured C++ code."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

from .ast import (
    BreakStmt,
    ExprStmt,
    ForRangeLoop,
    FunctionDef,
    IfStatement,
    LedBlink,
    LedDecl,
    LedFadeIn,
    LedFadeOut,
    LedFlashPattern,
    LedOff,
    LedOn,
    LedSetBrightness,
    LedToggle,
    Program,
    ReturnStmt,
    SerialMonitorDecl,
    SerialWrite,
    Sleep,
    UltrasonicDecl,
    TryStatement,
    VarAssign,
    VarDecl,
    WhileLoop,
)

try:
    from .ast import InfiniteLoop, Repeat
except Exception:  # pragma: no cover - compatibility shim
    class InfiniteLoop:  # type: ignore[too-many-ancestors]
        pass

    class Repeat:  # type: ignore[too-many-ancestors]
        pass


HEADER = """#include <Arduino.h>

"""

LEN_HELPER_SNIPPET = """#include <cstring>

template <typename T, size_t N>
constexpr size_t __redu_len(const T (&value)[N]) {
  return N;
}

inline size_t __redu_len(const char *value) {
  return strlen(value);
}

template <typename T>
auto __redu_len(const T &value) -> decltype(value.length()) {
  return value.length();
}
"""

LIST_HELPER_SNIPPET = """template <typename T>
struct __redu_list {
  T *data;
  size_t size;
  __redu_list() : data(nullptr), size(0) {}
};

template <typename T>
__redu_list<T> __redu_make_list() {
  return {};
}

template <typename T, typename First, typename... Rest>
__redu_list<T> __redu_make_list(First first, Rest... rest) {
  __redu_list<T> result;
  result.size = sizeof...(Rest) + 1;
  result.data = new T[result.size]{static_cast<T>(first), static_cast<T>(rest)...};
  return result;
}

template <typename T>
T &__redu_list_get(__redu_list<T> &list, int index) {
if (index < 0) {
    index += static_cast<int>(list.size);
  }
  return list.data[index];
}

template <typename T>
const T &__redu_list_get(const __redu_list<T> &list, int index) {
if (index < 0) {
    index += static_cast<int>(list.size);
  }
  return list.data[index];
}

template <typename T>
void __redu_list_append(__redu_list<T> &list, const T &value) {
  T *next = new T[list.size + 1];
  for (size_t i = 0; i < list.size; ++i) {
    next[i] = list.data[i];
  }
  next[list.size] = value;
  delete[] list.data;
  list.data = next;
  ++list.size;
}

template <typename T>
void __redu_list_remove(__redu_list<T> &list, const T &value) {
  if (list.size == 0) {
    return;
  }
  size_t remove_index = list.size;
  for (size_t i = 0; i < list.size; ++i) {
    if (list.data[i] == value) {
      remove_index = i;
      break;
    }
  }
  if (remove_index == list.size) {
    return;
  }
  T *next = nullptr;
  if (list.size > 1) {
    next = new T[list.size - 1];
    size_t dest = 0;
    for (size_t i = 0; i < list.size; ++i) {
      if (i == remove_index) {
        continue;
      }
      next[dest++] = list.data[i];
    }
  }
  delete[] list.data;
  list.data = next;
  --list.size;
}

template <typename T>
void __redu_list_assign(__redu_list<T> &dest, const __redu_list<T> &source) {
  if (&dest == &source) {
    return;
  }
  if (dest.data != nullptr) {
    delete[] dest.data;
  }
  dest.size = source.size;
  dest.data = dest.size ? new T[dest.size] : nullptr;
  for (size_t i = 0; i < dest.size; ++i) {
    dest.data[i] = source.data[i];
  }
}

template <typename T, typename Func>
__redu_list<T> __redu_list_from_range(int start, int stop, int step, Func func) {
  __redu_list<T> result;
  if (step == 0) {
    return result;
  }
  int count = 0;
  if (step > 0) {
    for (int value = start; value < stop; value += step) {
      ++count;
    }
  } else {
    for (int value = start; value > stop; value += step) {
      ++count;
    }
  }
  result.data = count > 0 ? new T[count] : nullptr;
  result.size = 0;
  if (step > 0) {
    for (int value = start; value < stop; value += step) {
      result.data[result.size++] = func(value);
    }
  } else {
    for (int value = start; value > stop; value += step) {
      result.data[result.size++] = func(value);
    }
  }
  return result;
}

template <typename T>
size_t __redu_len(const __redu_list<T> &value) {
  return value.size;
}
"""
SETUP_START = "void setup() {\n"
SETUP_END = "}\n\n"
LOOP_START = "void loop() {\n"
LOOP_END = "}\n"

def _emit_expr(v: Union[int, str]) -> str:
    """Render an integer literal or a pre-formatted expression string."""

    return str(v)

def _emit_block(
    nodes: Iterable[object],
    led_pin: Dict[str, Union[int, str]],
    led_state: Dict[str, str],
    led_brightness: Dict[str, str],
    ultrasonic_decls: Dict[str, UltrasonicDecl],
    indent: str = "  ",
    *,
    in_setup: bool = False,
    emitted_pin_modes: Optional[Set[Tuple[str, str]]] = None,
    ultrasonic_pin_modes: Optional[Set[Tuple[str, str, str]]] = None,
) -> List[str]:
    """Emit a block of statements as C++ source lines."""
    lines: List[str] = []
    for node in nodes:
        if type(node).__name__ == "Repeat":
            count = getattr(node, "count", 0)
            body = getattr(node, "body", [])
            lines.append(f"{indent}for (int __i = 0; __i < {count}; ++__i) {{")
            lines.extend(
                _emit_block(
                    body,
                    led_pin,
                    led_state,
                    led_brightness,
                    ultrasonic_decls,
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
                    ultrasonic_pin_modes=ultrasonic_pin_modes,
                )
            )
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, IfStatement):
            for idx, branch in enumerate(node.branches):
                keyword = "if" if idx == 0 else "else if"
                lines.append(f"{indent}{keyword} ({branch.condition}) {{")
                lines.extend(
                    _emit_block(
                        branch.body,
                        led_pin,
                        led_state,
                        led_brightness,
                        ultrasonic_decls,
                        indent + "  ",
                        in_setup=in_setup,
                        emitted_pin_modes=emitted_pin_modes,
                        ultrasonic_pin_modes=ultrasonic_pin_modes,
                    )
                )
                lines.append(f"{indent}}}")
            if node.else_body:
                lines.append(f"{indent}else {{")
                lines.extend(
                    _emit_block(
                        node.else_body,
                        led_pin,
                        led_state,
                        led_brightness,
                        ultrasonic_decls,
                        indent + "  ",
                        in_setup=in_setup,
                        emitted_pin_modes=emitted_pin_modes,
                        ultrasonic_pin_modes=ultrasonic_pin_modes,
                    )
                )
                lines.append(f"{indent}}}")
            continue

        if isinstance(node, WhileLoop):
            lines.append(f"{indent}while ({node.condition}) {{")
            lines.extend(
                _emit_block(
                    node.body,
                    led_pin,
                    led_state,
                    led_brightness,
                    ultrasonic_decls,
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
                    ultrasonic_pin_modes=ultrasonic_pin_modes,
                )
            )
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, ForRangeLoop):
            lines.append(
                f"{indent}for (int {node.var_name} = 0; {node.var_name} < {node.count}; ++{node.var_name}) {{"
            )
            lines.extend(
                _emit_block(
                    node.body,
                    led_pin,
                    led_state,
                    led_brightness,
                    ultrasonic_decls,
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
                    ultrasonic_pin_modes=ultrasonic_pin_modes,
                )
            )
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, TryStatement):
            lines.append(f"{indent}try {{")
            lines.extend(
                _emit_block(
                    node.try_body,
                    led_pin,
                    led_state,
                    led_brightness,
                    ultrasonic_decls,
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
                    ultrasonic_pin_modes=ultrasonic_pin_modes,
                )
            )
            lines.append(f"{indent}}}")

            for handler in node.handlers:
                if handler.exception:
                    exc_name = handler.exception.replace(".", "::")
                    if handler.target:
                        header = f"catch ({exc_name} &{handler.target})"
                    else:
                        header = f"catch ({exc_name} &)"
                else:
                    header = "catch (...)"
                lines.append(f"{indent}{header} {{")
                lines.extend(
                    _emit_block(
                        handler.body,
                        led_pin,
                        led_state,
                        led_brightness,
                        ultrasonic_decls,
                        indent + "  ",
                        in_setup=in_setup,
                        emitted_pin_modes=emitted_pin_modes,
                        ultrasonic_pin_modes=ultrasonic_pin_modes,
                    )
                )
                lines.append(f"{indent}}}")
            continue

        if isinstance(node, SerialMonitorDecl):
            lines.append(f"{indent}Serial.begin({_emit_expr(node.baud)});")
            continue

        if isinstance(node, SerialWrite):
            method = "println" if getattr(node, "newline", True) else "print"
            lines.append(f"{indent}Serial.{method}({node.value});")
            continue

        if isinstance(node, VarDecl):
            if node.global_scope:
                continue
            lines.append(f"{indent}{node.c_type} {node.name} = {node.expr};")
            continue

        if isinstance(node, VarAssign):
            lines.append(f"{indent}{node.name} = {node.expr};")
            continue

        if isinstance(node, ExprStmt):
            lines.append(f"{indent}{node.expr};")
            continue

        if isinstance(node, ReturnStmt):
            if node.expr is None:
                lines.append(f"{indent}return;")
            else:
                lines.append(f"{indent}return {node.expr};")
            continue

        if isinstance(node, BreakStmt):
            lines.append(f"{indent}break;")
            continue

        def _ensure_led_tracking(name: str) -> Tuple[str, str, str]:
            pin = led_pin.get(name, 13)
            state_var = led_state.setdefault(name, f"__state_{name}")
            brightness_var = led_brightness.setdefault(name, f"__brightness_{name}")
            return _emit_expr(pin), state_var, brightness_var

        if isinstance(node, LedDecl):
            led_pin[node.name] = node.pin
            led_state[node.name] = f"__state_{node.name}"
            led_brightness[node.name] = f"__brightness_{node.name}"
            if in_setup:
                if emitted_pin_modes is None:
                    emitted_pin_modes = set()
                pin_expr = _emit_expr(node.pin)
                key = (node.name, pin_expr)
                if key not in emitted_pin_modes:
                    emitted_pin_modes.add(key)
                    lines.append(f"{indent}pinMode({pin_expr}, OUTPUT);")
            continue

        if isinstance(node, UltrasonicDecl):
            ultrasonic_decls[node.name] = node
            if in_setup:
                if ultrasonic_pin_modes is None:
                    ultrasonic_pin_modes = set()
                trig_expr = _emit_expr(node.trig)
                echo_expr = _emit_expr(node.echo)
                trig_key = (node.name, trig_expr, "OUTPUT")
                if trig_key not in ultrasonic_pin_modes:
                    ultrasonic_pin_modes.add(trig_key)
                    lines.append(f"{indent}pinMode({trig_expr}, OUTPUT);")
                echo_key = (node.name, echo_expr, "INPUT")
                if echo_key not in ultrasonic_pin_modes:
                    ultrasonic_pin_modes.add(echo_key)
                    lines.append(f"{indent}pinMode({echo_expr}, INPUT);")
            continue

        if isinstance(node, LedOn):
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            lines.append(f"{indent}{state_var} = true;")
            lines.append(f"{indent}{brightness_var} = 255;")
            lines.append(f"{indent}digitalWrite({pin_code}, HIGH);")
            continue

        if isinstance(node, LedOff):
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            lines.append(f"{indent}{state_var} = false;")
            lines.append(f"{indent}{brightness_var} = 0;")
            lines.append(f"{indent}digitalWrite({pin_code}, LOW);")
            continue

        if isinstance(node, LedToggle):
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            lines.append(f"{indent}{state_var} = !{state_var};")
            lines.append(f"{indent}{brightness_var} = {state_var} ? 255 : 0;")
            lines.append(
                f"{indent}digitalWrite({pin_code}, {state_var} ? HIGH : LOW);"
            )
            continue

        if isinstance(node, LedSetBrightness):
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            value_expr = _emit_expr(node.value)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  int __redu_brightness = {value_expr};")
            lines.append(f"{indent}  if (__redu_brightness < 0) {{ __redu_brightness = 0; }}")
            lines.append(f"{indent}  if (__redu_brightness > 255) {{ __redu_brightness = 255; }}")
            lines.append(f"{indent}  {brightness_var} = __redu_brightness;")
            lines.append(f"{indent}  {state_var} = {brightness_var} > 0;")
            lines.append(f"{indent}  analogWrite({pin_code}, {brightness_var});")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, LedBlink):
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            duration_expr = _emit_expr(node.duration_ms)
            times_expr = _emit_expr(node.times)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  int __redu_times = {times_expr};")
            lines.append(f"{indent}  if (__redu_times < 0) {{ __redu_times = 0; }}")
            lines.append(f"{indent}  for (int __redu_i = 0; __redu_i < __redu_times; ++__redu_i) {{")
            lines.append(f"{indent}    {state_var} = true;")
            lines.append(f"{indent}    {brightness_var} = 255;")
            lines.append(f"{indent}    digitalWrite({pin_code}, HIGH);")
            lines.append(f"{indent}    delay({duration_expr});")
            lines.append(f"{indent}    {state_var} = false;")
            lines.append(f"{indent}    {brightness_var} = 0;")
            lines.append(f"{indent}    digitalWrite({pin_code}, LOW);")
            lines.append(f"{indent}    delay({duration_expr});")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}  {state_var} = false;")
            lines.append(f"{indent}  {brightness_var} = 0;")
            lines.append(f"{indent}  digitalWrite({pin_code}, LOW);")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, LedFadeIn):
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            step_expr = _emit_expr(node.step)
            delay_expr = _emit_expr(node.delay_ms)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  int __redu_step = {step_expr};")
            lines.append(f"{indent}  if (__redu_step <= 0) {{ __redu_step = 1; }}")
            lines.append(f"{indent}  int __redu_value = {brightness_var};")
            lines.append(f"{indent}  if (__redu_value < 0) {{ __redu_value = 0; }}")
            lines.append(f"{indent}  if (__redu_value > 255) {{ __redu_value = 255; }}")
            lines.append(f"{indent}  while (__redu_value < 255) {{")
            lines.append(f"{indent}    {brightness_var} = __redu_value;")
            lines.append(f"{indent}    {state_var} = {brightness_var} > 0;")
            lines.append(f"{indent}    analogWrite({pin_code}, {brightness_var});")
            lines.append(f"{indent}    delay({delay_expr});")
            lines.append(f"{indent}    __redu_value += __redu_step;")
            lines.append(f"{indent}    if (__redu_value > 255) {{ __redu_value = 255; }}")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}  {brightness_var} = 255;")
            lines.append(f"{indent}  {state_var} = true;")
            lines.append(f"{indent}  analogWrite({pin_code}, 255);")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, LedFadeOut):
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            step_expr = _emit_expr(node.step)
            delay_expr = _emit_expr(node.delay_ms)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  int __redu_step = {step_expr};")
            lines.append(f"{indent}  if (__redu_step <= 0) {{ __redu_step = 1; }}")
            lines.append(f"{indent}  int __redu_value = {brightness_var};")
            lines.append(f"{indent}  if (__redu_value < 0) {{ __redu_value = 0; }}")
            lines.append(f"{indent}  if (__redu_value > 255) {{ __redu_value = 255; }}")
            lines.append(f"{indent}  while (__redu_value > 0) {{")
            lines.append(f"{indent}    {brightness_var} = __redu_value;")
            lines.append(f"{indent}    {state_var} = {brightness_var} > 0;")
            lines.append(f"{indent}    analogWrite({pin_code}, {brightness_var});")
            lines.append(f"{indent}    delay({delay_expr});")
            lines.append(f"{indent}    __redu_value -= __redu_step;")
            lines.append(f"{indent}    if (__redu_value < 0) {{ __redu_value = 0; }}")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}  {brightness_var} = 0;")
            lines.append(f"{indent}  {state_var} = false;")
            lines.append(f"{indent}  analogWrite({pin_code}, 0);")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, LedFlashPattern):
            if not node.pattern:
                continue
            pin_code, state_var, brightness_var = _ensure_led_tracking(node.name)
            delay_expr = _emit_expr(node.delay_ms)
            pattern_values = ", ".join(str(int(v)) for v in node.pattern)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  const int __redu_pattern[] = {{{pattern_values}}};")
            lines.append(
                f"{indent}  const size_t __redu_pattern_len = sizeof(__redu_pattern) / sizeof(__redu_pattern[0]);"
            )
            lines.append(f"{indent}  for (size_t __redu_i = 0; __redu_i < __redu_pattern_len; ++__redu_i) {{")
            lines.append(f"{indent}    int __redu_value = __redu_pattern[__redu_i];")
            lines.append(f"{indent}    if (__redu_value <= 0) {{")
            lines.append(f"{indent}      {brightness_var} = 0;")
            lines.append(f"{indent}      {state_var} = false;")
            lines.append(f"{indent}      digitalWrite({pin_code}, LOW);")
            lines.append(f"{indent}    }} else if (__redu_value == 1) {{")
            lines.append(f"{indent}      {brightness_var} = 255;")
            lines.append(f"{indent}      {state_var} = true;")
            lines.append(f"{indent}      digitalWrite({pin_code}, HIGH);")
            lines.append(f"{indent}    }} else {{")
            lines.append(f"{indent}      if (__redu_value > 255) {{ __redu_value = 255; }}")
            lines.append(f"{indent}      {brightness_var} = __redu_value;")
            lines.append(f"{indent}      {state_var} = {brightness_var} > 0;")
            lines.append(f"{indent}      analogWrite({pin_code}, {brightness_var});")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}    if (__redu_i + 1 < __redu_pattern_len) {{")
            lines.append(f"{indent}      delay({delay_expr});")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, Sleep):
            lines.append(f"{indent}delay({_emit_expr(node.ms)});")

    return lines

def emit(ast: Program) -> str:
    """Serialize a :class:`~Reduino.transpile.ast.Program` into Arduino C++."""

    led_pin: Dict[str, Union[int, str]] = {}
    led_state: Dict[str, str] = {}
    led_brightness: Dict[str, str] = {}
    helpers = getattr(ast, "helpers", set())
    ultrasonic_measurements = getattr(ast, "ultrasonic_measurements", set())

    globals_: List[str] = []
    setup_lines: List[str] = []
    loop_lines: List[str] = []

    ultrasonic_decls: Dict[str, UltrasonicDecl] = {}
    ultrasonic_pin_modes: Set[Tuple[str, str, str]] = set()
    loop_ultrasonic_modes: Set[Tuple[str, str, str]] = set()

    for decl in getattr(ast, "global_decls", []):
        line = f"{decl.c_type} {decl.name} = {decl.expr};"
        if line not in globals_:
            globals_.append(line)

    # Back-compat: if parser hasn't split, treat body as setup
    setup_body = getattr(ast, "setup_body", None)
    loop_body = getattr(ast, "loop_body", None)
    if setup_body is None and loop_body is None:
        setup_body = getattr(ast, "body", [])
        loop_body = []

    # Pass 1: collect LED declarations to create globals & pinModes in setup()
    pin_mode_emitted: Set[Tuple[str, str]] = set()

    for node in (setup_body or []):
        if isinstance(node, LedDecl):
            state_var = f"__state_{node.name}"
            bright_var = f"__brightness_{node.name}"
            led_state[node.name] = state_var
            led_brightness[node.name] = bright_var
            state_line = f"bool {state_var} = false;"
            if state_line not in globals_:
                globals_.append(state_line)
            bright_line = f"int {bright_var} = 0;"
            if bright_line not in globals_:
                globals_.append(bright_line)
            led_pin[node.name] = node.pin
        if isinstance(node, UltrasonicDecl):
            ultrasonic_decls[node.name] = node

    for node in (loop_body or []):
        if isinstance(node, LedDecl):
            state_var = f"__state_{node.name}"
            bright_var = f"__brightness_{node.name}"
            if node.name not in led_state:
                led_state[node.name] = state_var
                state_line = f"bool {state_var} = false;"
                if state_line not in globals_:
                    globals_.append(state_line)
            if node.name not in led_brightness:
                led_brightness[node.name] = bright_var
                bright_line = f"int {bright_var} = 0;"
                if bright_line not in globals_:
                    globals_.append(bright_line)
            if node.name not in led_pin:
                led_pin[node.name] = node.pin
            # Ensure pinMode exists in setup for pins declared in loop
            setup_lines.append(f"  pinMode({_emit_expr(node.pin)}, OUTPUT);")
        if isinstance(node, UltrasonicDecl):
            if node.name not in ultrasonic_decls:
                ultrasonic_decls[node.name] = node
            trig_expr = _emit_expr(node.trig)
            echo_expr = _emit_expr(node.echo)
            trig_key = (node.name, trig_expr, "OUTPUT")
            echo_key = (node.name, echo_expr, "INPUT")
            if trig_key not in loop_ultrasonic_modes:
                loop_ultrasonic_modes.add(trig_key)
                setup_lines.append(f"  pinMode({trig_expr}, OUTPUT);")
            if echo_key not in loop_ultrasonic_modes:
                loop_ultrasonic_modes.add(echo_key)
                setup_lines.append(f"  pinMode({echo_expr}, INPUT);")

    # Pass 2: emit statements
    setup_lines.extend(
        _emit_block(
            setup_body or [],
            led_pin,
            led_state,
            led_brightness,
            ultrasonic_decls,
            in_setup=True,
            emitted_pin_modes=pin_mode_emitted,
            ultrasonic_pin_modes=ultrasonic_pin_modes,
        )
    )

    # If someone encoded an InfiniteLoop in setup, emit its body into loop()
    infinite_nodes = [n for n in (setup_body or []) if type(n).__name__ == "InfiniteLoop"]
    if infinite_nodes:
        for n in infinite_nodes:
            loop_lines.extend(
                _emit_block(
                    getattr(n, "body", []),
                    led_pin,
                    led_state,
                    led_brightness,
                    ultrasonic_decls,
                    in_setup=False,
                    emitted_pin_modes=pin_mode_emitted,
                    ultrasonic_pin_modes=ultrasonic_pin_modes,
                )
            )

    # Normal loop body (preferred path)
    loop_lines.extend(
        _emit_block(
            loop_body or [],
            led_pin,
            led_state,
            led_brightness,
            ultrasonic_decls,
            in_setup=False,
            emitted_pin_modes=pin_mode_emitted,
            ultrasonic_pin_modes=ultrasonic_pin_modes,
        )
    )

    function_sections: List[str] = []
    for fn in getattr(ast, "functions", []):
        params_src = ", ".join(f"{ptype} {name}" for name, ptype in fn.params)
        header = f"{fn.return_type} {fn.name}({params_src}) {{\n"
        body_lines = _emit_block(
            getattr(fn, "body", []),
            dict(led_pin),
            dict(led_state),
            dict(led_brightness),
            ultrasonic_decls,
            indent="  ",
            in_setup=False,
            emitted_pin_modes=set(),
            ultrasonic_pin_modes=set(),
        )
        function_sections.append(header)
        if body_lines:
            function_sections.append("\n".join(body_lines))
            function_sections.append("\n")
        function_sections.append("}\n\n")

    ultrasonic_sections: List[str] = []
    for name in sorted(ultrasonic_measurements):
        decl = ultrasonic_decls.get(name)
        if decl is None:
            continue
        trig_expr = _emit_expr(decl.trig)
        echo_expr = _emit_expr(decl.echo)
        helper_lines = [
            f"float __redu_ultrasonic_measure_{name}() {{",
            f"  digitalWrite({trig_expr}, LOW);",
            "  delayMicroseconds(2);",
            f"  digitalWrite({trig_expr}, HIGH);",
            "  delayMicroseconds(10);",
            f"  digitalWrite({trig_expr}, LOW);",
            f"  unsigned long __redu_duration_{name} = pulseIn({echo_expr}, HIGH);",
            f"  return (static_cast<float>(__redu_duration_{name}) * 0.0343f) / 2.0f;",
            "}\n",
        ]
        ultrasonic_sections.append("\n".join(helper_lines))

    # Stitch sections
    parts: List[str] = [HEADER]
    if "list" in helpers:
        parts.append(LIST_HELPER_SNIPPET + "\n")
    if "len" in helpers:
        parts.append(LEN_HELPER_SNIPPET + "\n")
    if globals_:
        parts.append("\n".join(globals_) + "\n\n")
    if function_sections:
        parts.append("".join(function_sections))
    if ultrasonic_sections:
        parts.append("".join(ultrasonic_sections))

    parts.append(SETUP_START)
    parts.append("\n".join(setup_lines) if setup_lines else "  // no setup actions")
    parts.append("\n" + SETUP_END)

    parts.append(LOOP_START)
    parts.append("\n".join(loop_lines) if loop_lines else "  // no loop actions")
    parts.append("\n" + LOOP_END)

    return "".join(parts)
