"""Translate Reduino AST nodes into Arduino-flavoured C++ code."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

from .ast import (
    BreakStmt,
    ButtonDecl,
    ButtonPoll,
    ExprStmt,
    ForRangeLoop,
    FunctionDef,
    BuzzerBeep,
    BuzzerDecl,
    BuzzerMelody,
    BuzzerPlayTone,
    BuzzerStop,
    BuzzerSweep,
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
    RGBLedBlink,
    RGBLedDecl,
    RGBLedFade,
    RGBLedOff,
    RGBLedOn,
    RGBLedSetColor,
    ServoDecl,
    ServoWrite,
    ServoWriteMicroseconds,
    PotentiometerDecl,
    ReturnStmt,
    SerialMonitorDecl,
    SerialWrite,
    Sleep,
    TryStatement,
    UltrasonicDecl,
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

def _emit_expr(v: Union[int, float, str]) -> str:
    """Render an integer literal or a pre-formatted expression string."""

    return str(v)


def _format_float(value: float) -> str:
    """Format a float literal suitable for C++ source emission."""

    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    if "e" not in text.lower() and "." not in text:
        text += ".0"
    return f"{text}f"


_BUZZER_MELODIES = {
    "success": {
        "tempo": 240.0,
        "sequence": [(523.25, 0.5), (659.25, 0.5), (783.99, 1.0)],
    },
    "error": {"tempo": 200.0, "sequence": [(329.63, 0.5), (261.63, 1.5)]},
    "startup": {
        "tempo": 200.0,
        "sequence": [(261.63, 0.5), (329.63, 0.5), (392.0, 0.5), (523.25, 1.0)],
    },
    "notify": {
        "tempo": 240.0,
        "sequence": [(783.99, 0.25), (0.0, 0.25), (783.99, 0.5)],
    },
    "alarm": {
        "tempo": 200.0,
        "sequence": [
            (523.25, 0.5),
            (392.0, 0.5),
            (523.25, 0.5),
            (392.0, 0.5),
            (523.25, 0.5),
            (392.0, 0.5),
            (523.25, 0.5),
            (392.0, 0.5),
        ],
    },
    "scale_c": {
        "tempo": 200.0,
        "sequence": [
            (261.63, 0.5),
            (293.66, 0.5),
            (329.63, 0.5),
            (349.23, 0.5),
            (392.0, 0.5),
            (440.0, 0.5),
            (493.88, 0.5),
            (523.25, 1.0),
        ],
    },
    "siren": {
        "tempo": 180.0,
        "sequence": [
            (659.25, 0.75),
            (523.25, 0.75),
            (659.25, 0.75),
            (523.25, 0.75),
            (659.25, 0.75),
            (523.25, 0.75),
        ],
    },
}

def _emit_block(
    nodes: Iterable[object],
    led_pin: Dict[str, Union[int, str]],
    led_state: Dict[str, str],
    led_brightness: Dict[str, str],
    buzzer_pin: Dict[str, Union[int, str]],
    buzzer_state: Dict[str, str],
    buzzer_current: Dict[str, str],
    buzzer_last: Dict[str, str],
    rgb_led_pins: Dict[str, Tuple[Union[int, str], Union[int, str], Union[int, str]]],
    rgb_led_state: Dict[str, str],
    rgb_led_colors: Dict[str, Tuple[str, str, str]],
    ultrasonic_decls: Dict[str, UltrasonicDecl],
    potentiometer_decls: Dict[str, PotentiometerDecl],
    button_decls: Dict[str, ButtonDecl],
    servo_decls: Dict[str, ServoDecl],
    servo_state: Dict[str, Dict[str, str]],
    indent: str = "  ",
    *,
    in_setup: bool = False,
    emitted_pin_modes: Optional[Set[Tuple[str, ...]]] = None,
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
                    buzzer_pin,
                    buzzer_state,
                    buzzer_current,
                    buzzer_last,
                    rgb_led_pins,
                    rgb_led_state,
                    rgb_led_colors,
                    ultrasonic_decls,
                    potentiometer_decls,
                    button_decls,
                    servo_decls,
                    servo_state,
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
                    ultrasonic_pin_modes=ultrasonic_pin_modes,
                )
            )
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, ButtonDecl):
            continue

        if isinstance(node, ButtonPoll):
            decl = button_decls.get(node.name)
            if decl is None:
                continue
            pin_expr = _emit_expr(decl.pin)
            next_var = f"__redu_button_next_{node.name}"
            prev_var = f"__redu_button_prev_{node.name}"
            value_var = f"__redu_button_value_{node.name}"
            lines.append(
                f"{indent}bool {next_var} = (digitalRead({pin_expr}) == HIGH);"
            )
            if decl.on_click:
                lines.append(f"{indent}if ({next_var} && !{prev_var}) {{")
                lines.append(f"{indent}  {decl.on_click}();")
                lines.append(f"{indent}}}")
            lines.append(f"{indent}{prev_var} = {next_var};")
            lines.append(f"{indent}{value_var} = {next_var};")
            continue

        if isinstance(node, ServoDecl):
            servo_decls.setdefault(node.name, node)
            continue

        if isinstance(node, PotentiometerDecl):
            potentiometer_decls[node.name] = node
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
                    buzzer_pin,
                    buzzer_state,
                    buzzer_current,
                    buzzer_last,
                    rgb_led_pins,
                    rgb_led_state,
                    rgb_led_colors,
                    ultrasonic_decls,
                    potentiometer_decls,
                    button_decls,
                    servo_decls,
                    servo_state,
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
                        buzzer_pin,
                        buzzer_state,
                        buzzer_current,
                        buzzer_last,
                        rgb_led_pins,
                        rgb_led_state,
                        rgb_led_colors,
                        ultrasonic_decls,
                        potentiometer_decls,
                        button_decls,
                        servo_decls,
                        servo_state,
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
                    buzzer_pin,
                    buzzer_state,
                    buzzer_current,
                    buzzer_last,
                    rgb_led_pins,
                    rgb_led_state,
                    rgb_led_colors,
                    ultrasonic_decls,
                    potentiometer_decls,
                    button_decls,
                    servo_decls,
                    servo_state,
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
                    buzzer_pin,
                    buzzer_state,
                    buzzer_current,
                    buzzer_last,
                    rgb_led_pins,
                    rgb_led_state,
                    rgb_led_colors,
                    ultrasonic_decls,
                    potentiometer_decls,
                    button_decls,
                    servo_decls,
                    servo_state,
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
                    buzzer_pin,
                    buzzer_state,
                    buzzer_current,
                    buzzer_last,
                    rgb_led_pins,
                    rgb_led_state,
                    rgb_led_colors,
                    ultrasonic_decls,
                    potentiometer_decls,
                    button_decls,
                    servo_decls,
                    servo_state,
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
                        buzzer_pin,
                        buzzer_state,
                        buzzer_current,
                        buzzer_last,
                        rgb_led_pins,
                        rgb_led_state,
                        rgb_led_colors,
                        ultrasonic_decls,
                        potentiometer_decls,
                        button_decls,
                        servo_decls,
                        servo_state,
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

        def _ensure_buzzer_tracking(name: str) -> Tuple[str, str, str, str]:
            pin_value = buzzer_pin.get(name, 8)
            pin_code = _emit_expr(pin_value)
            state_var = buzzer_state.setdefault(name, f"__buzzer_state_{name}")
            current_var = buzzer_current.setdefault(name, f"__buzzer_current_{name}")
            last_var = buzzer_last.setdefault(name, f"__buzzer_last_{name}")
            return pin_code, state_var, current_var, last_var

        def _ensure_led_tracking(name: str) -> Tuple[str, str, str]:
            pin = led_pin.get(name, 13)
            state_var = led_state.setdefault(name, f"__state_{name}")
            brightness_var = led_brightness.setdefault(name, f"__brightness_{name}")
            return _emit_expr(pin), state_var, brightness_var

        def _ensure_rgb_tracking(name: str) -> Tuple[Tuple[str, str, str], Tuple[str, str, str], str]:
            pins = rgb_led_pins.get(name)
            if pins is None:
                pins = (0, 0, 0)
            pin_codes = tuple(_emit_expr(pin) for pin in pins)
            state_var = rgb_led_state.setdefault(name, f"__rgb_state_{name}")
            color_vars = rgb_led_colors.setdefault(
                name,
                (
                    f"__rgb_red_{name}",
                    f"__rgb_green_{name}",
                    f"__rgb_blue_{name}",
                ),
            )
            return pin_codes, color_vars, state_var

        def _emit_rgb_update(name: str, red_expr: str, green_expr: str, blue_expr: str) -> List[str]:
            pin_codes, color_vars, state_var = _ensure_rgb_tracking(name)
            red_pin, green_pin, blue_pin = pin_codes
            red_var, green_var, blue_var = color_vars
            block_lines = [f"{indent}{{"]
            block_lines.append(f"{indent}  int __redu_red = {red_expr};")
            block_lines.append(f"{indent}  if (__redu_red < 0) {{ __redu_red = 0; }}")
            block_lines.append(f"{indent}  if (__redu_red > 255) {{ __redu_red = 255; }}")
            block_lines.append(f"{indent}  int __redu_green = {green_expr};")
            block_lines.append(f"{indent}  if (__redu_green < 0) {{ __redu_green = 0; }}")
            block_lines.append(f"{indent}  if (__redu_green > 255) {{ __redu_green = 255; }}")
            block_lines.append(f"{indent}  int __redu_blue = {blue_expr};")
            block_lines.append(f"{indent}  if (__redu_blue < 0) {{ __redu_blue = 0; }}")
            block_lines.append(f"{indent}  if (__redu_blue > 255) {{ __redu_blue = 255; }}")
            block_lines.append(f"{indent}  {red_var} = __redu_red;")
            block_lines.append(f"{indent}  {green_var} = __redu_green;")
            block_lines.append(f"{indent}  {blue_var} = __redu_blue;")
            block_lines.append(
                f"{indent}  {state_var} = (({red_var} > 0) || ({green_var} > 0) || ({blue_var} > 0));"
            )
            block_lines.append(f"{indent}  analogWrite({red_pin}, {red_var});")
            block_lines.append(f"{indent}  analogWrite({green_pin}, {green_var});")
            block_lines.append(f"{indent}  analogWrite({blue_pin}, {blue_var});")
            block_lines.append(f"{indent}}}")
            return block_lines

        def _ensure_servo_tracking(
            name: str,
        ) -> Tuple[str, str, str, str, str, str, str]:
            info = servo_state.setdefault(
                name,
                {
                    "object": f"__servo_{name}",
                    "min_angle": f"__servo_min_angle_{name}",
                    "max_angle": f"__servo_max_angle_{name}",
                    "min_pulse": f"__servo_min_pulse_{name}",
                    "max_pulse": f"__servo_max_pulse_{name}",
                    "angle": f"__servo_angle_{name}",
                    "pulse": f"__servo_pulse_{name}",
                },
            )
            return (
                info["object"],
                info["min_angle"],
                info["max_angle"],
                info["min_pulse"],
                info["max_pulse"],
                info["angle"],
                info["pulse"],
            )

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

        if isinstance(node, BuzzerDecl):
            buzzer_pin[node.name] = node.pin
            buzzer_state.setdefault(node.name, f"__buzzer_state_{node.name}")
            buzzer_current.setdefault(node.name, f"__buzzer_current_{node.name}")
            buzzer_last.setdefault(node.name, f"__buzzer_last_{node.name}")
            if in_setup:
                if emitted_pin_modes is None:
                    emitted_pin_modes = set()
                pin_expr = _emit_expr(node.pin)
                key = (node.name, pin_expr, "OUTPUT")
                if key not in emitted_pin_modes:
                    emitted_pin_modes.add(key)
                    lines.append(f"{indent}pinMode({pin_expr}, OUTPUT);")
            continue

        if isinstance(node, RGBLedDecl):
            rgb_led_pins[node.name] = (node.red_pin, node.green_pin, node.blue_pin)
            rgb_led_state.setdefault(node.name, f"__rgb_state_{node.name}")
            rgb_led_colors.setdefault(
                node.name,
                (
                    f"__rgb_red_{node.name}",
                    f"__rgb_green_{node.name}",
                    f"__rgb_blue_{node.name}",
                ),
            )
            if in_setup:
                if emitted_pin_modes is None:
                    emitted_pin_modes = set()
                for idx, pin in enumerate((node.red_pin, node.green_pin, node.blue_pin)):
                    pin_expr = _emit_expr(pin)
                    key = (node.name, pin_expr, str(idx))
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

        if isinstance(node, ServoWrite):
            (
                servo_obj,
                min_angle_var,
                max_angle_var,
                min_pulse_var,
                max_pulse_var,
                angle_var,
                pulse_var,
            ) = _ensure_servo_tracking(node.name)
            angle_expr = _emit_expr(node.angle)
            lines.append(f"{indent}{{")
            lines.append(
                f"{indent}  float __redu_angle = static_cast<float>({angle_expr});"
            )
            lines.append(
                f"{indent}  if (__redu_angle < {min_angle_var}) {{ __redu_angle = {min_angle_var}; }}"
            )
            lines.append(
                f"{indent}  if (__redu_angle > {max_angle_var}) {{ __redu_angle = {max_angle_var}; }}"
            )
            lines.append(f"{indent}  {angle_var} = __redu_angle;")
            lines.append(
                f"{indent}  float __redu_span = {max_angle_var} - {min_angle_var};"
            )
            lines.append(
                f"{indent}  if (__redu_span == 0.0f) {{ __redu_span = 1.0f; }}"
            )
            lines.append(
                f"{indent}  float __redu_pulse = {min_pulse_var} + ((__redu_angle - {min_angle_var}) / __redu_span) * ({max_pulse_var} - {min_pulse_var});"
            )
            lines.append(
                f"{indent}  if (__redu_pulse < {min_pulse_var}) {{ __redu_pulse = {min_pulse_var}; }}"
            )
            lines.append(
                f"{indent}  if (__redu_pulse > {max_pulse_var}) {{ __redu_pulse = {max_pulse_var}; }}"
            )
            lines.append(f"{indent}  {pulse_var} = __redu_pulse;")
            lines.append(
                f"{indent}  {servo_obj}.write(static_cast<int>(__redu_angle + 0.5f));"
            )
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, ServoWriteMicroseconds):
            (
                servo_obj,
                min_angle_var,
                max_angle_var,
                min_pulse_var,
                max_pulse_var,
                angle_var,
                pulse_var,
            ) = _ensure_servo_tracking(node.name)
            pulse_expr = _emit_expr(node.pulse_us)
            lines.append(f"{indent}{{")
            lines.append(
                f"{indent}  float __redu_pulse = static_cast<float>({pulse_expr});"
            )
            lines.append(
                f"{indent}  if (__redu_pulse < {min_pulse_var}) {{ __redu_pulse = {min_pulse_var}; }}"
            )
            lines.append(
                f"{indent}  if (__redu_pulse > {max_pulse_var}) {{ __redu_pulse = {max_pulse_var}; }}"
            )
            lines.append(f"{indent}  {pulse_var} = __redu_pulse;")
            lines.append(
                f"{indent}  float __redu_span = {max_pulse_var} - {min_pulse_var};"
            )
            lines.append(
                f"{indent}  if (__redu_span == 0.0f) {{ __redu_span = 1.0f; }}"
            )
            lines.append(
                f"{indent}  float __redu_angle = {min_angle_var} + ((__redu_pulse - {min_pulse_var}) / __redu_span) * ({max_angle_var} - {min_angle_var});"
            )
            lines.append(f"{indent}  {angle_var} = __redu_angle;")
            lines.append(
                f"{indent}  {servo_obj}.writeMicroseconds(static_cast<int>({pulse_var} + 0.5f));"
            )
            lines.append(f"{indent}}}")
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

        if isinstance(node, RGBLedSetColor):
            lines.extend(
                _emit_rgb_update(
                    node.name,
                    _emit_expr(node.red),
                    _emit_expr(node.green),
                    _emit_expr(node.blue),
                )
            )
            continue

        if isinstance(node, RGBLedOn):
            lines.extend(
                _emit_rgb_update(
                    node.name,
                    _emit_expr(node.red),
                    _emit_expr(node.green),
                    _emit_expr(node.blue),
                )
            )
            continue

        if isinstance(node, RGBLedOff):
            lines.extend(
                _emit_rgb_update(
                    node.name,
                    "0",
                    "0",
                    "0",
                )
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

        if isinstance(node, RGBLedFade):
            pin_codes, color_vars, state_var = _ensure_rgb_tracking(node.name)
            red_pin, green_pin, blue_pin = pin_codes
            red_var, green_var, blue_var = color_vars
            target_red = _emit_expr(node.red)
            target_green = _emit_expr(node.green)
            target_blue = _emit_expr(node.blue)
            duration_expr = _emit_expr(node.duration_ms)
            steps_expr = _emit_expr(node.steps)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  long __redu_duration = {duration_expr};")
            lines.append(f"{indent}  if (__redu_duration < 0L) {{ __redu_duration = 0L; }}")
            lines.append(f"{indent}  int __redu_steps = {steps_expr};")
            lines.append(f"{indent}  if (__redu_steps <= 0) {{ __redu_steps = 1; }}")
            lines.append(f"{indent}  int __redu_start_red = {red_var};")
            lines.append(f"{indent}  int __redu_start_green = {green_var};")
            lines.append(f"{indent}  int __redu_start_blue = {blue_var};")
            lines.append(f"{indent}  int __redu_target_red = {target_red};")
            lines.append(f"{indent}  if (__redu_target_red < 0) {{ __redu_target_red = 0; }}")
            lines.append(f"{indent}  if (__redu_target_red > 255) {{ __redu_target_red = 255; }}")
            lines.append(f"{indent}  int __redu_target_green = {target_green};")
            lines.append(f"{indent}  if (__redu_target_green < 0) {{ __redu_target_green = 0; }}")
            lines.append(f"{indent}  if (__redu_target_green > 255) {{ __redu_target_green = 255; }}")
            lines.append(f"{indent}  int __redu_target_blue = {target_blue};")
            lines.append(f"{indent}  if (__redu_target_blue < 0) {{ __redu_target_blue = 0; }}")
            lines.append(f"{indent}  if (__redu_target_blue > 255) {{ __redu_target_blue = 255; }}")
            lines.append(
                f"{indent}  bool __redu_same = (({red_var} == __redu_target_red) && ({green_var} == __redu_target_green) && ({blue_var} == __redu_target_blue));"
            )
            lines.append(f"{indent}  if ((__redu_duration == 0L) || __redu_same) {{")
            lines.append(f"{indent}    {red_var} = __redu_target_red;")
            lines.append(f"{indent}    {green_var} = __redu_target_green;")
            lines.append(f"{indent}    {blue_var} = __redu_target_blue;")
            lines.append(
                f"{indent}    {state_var} = (({red_var} > 0) || ({green_var} > 0) || ({blue_var} > 0));"
            )
            lines.append(f"{indent}    analogWrite({red_pin}, {red_var});")
            lines.append(f"{indent}    analogWrite({green_pin}, {green_var});")
            lines.append(f"{indent}    analogWrite({blue_pin}, {blue_var});")
            lines.append(f"{indent}  }} else {{")
            lines.append(
                f"{indent}    float __redu_step_delay = static_cast<float>(__redu_duration) / static_cast<float>(__redu_steps);"
            )
            lines.append(
                f"{indent}    unsigned long __redu_delay_ms = (__redu_step_delay <= 0.0f) ? 0UL : static_cast<unsigned long>(__redu_step_delay + 0.5f);"
            )
            lines.append(f"{indent}    for (int __redu_i = 1; __redu_i <= __redu_steps; ++__redu_i) {{")
            lines.append(
                f"{indent}      long __redu_num_red = static_cast<long>(__redu_target_red - __redu_start_red) * __redu_i;"
            )
            lines.append(f"{indent}      if (__redu_num_red >= 0L) {{ __redu_num_red += __redu_steps / 2; }}")
            lines.append(f"{indent}      else {{ __redu_num_red -= __redu_steps / 2; }}")
            lines.append(f"{indent}      int __redu_red = __redu_start_red + static_cast<int>(__redu_num_red / __redu_steps);")
            lines.append(
                f"{indent}      long __redu_num_green = static_cast<long>(__redu_target_green - __redu_start_green) * __redu_i;"
            )
            lines.append(f"{indent}      if (__redu_num_green >= 0L) {{ __redu_num_green += __redu_steps / 2; }}")
            lines.append(f"{indent}      else {{ __redu_num_green -= __redu_steps / 2; }}")
            lines.append(f"{indent}      int __redu_green = __redu_start_green + static_cast<int>(__redu_num_green / __redu_steps);")
            lines.append(
                f"{indent}      long __redu_num_blue = static_cast<long>(__redu_target_blue - __redu_start_blue) * __redu_i;"
            )
            lines.append(f"{indent}      if (__redu_num_blue >= 0L) {{ __redu_num_blue += __redu_steps / 2; }}")
            lines.append(f"{indent}      else {{ __redu_num_blue -= __redu_steps / 2; }}")
            lines.append(f"{indent}      int __redu_blue = __redu_start_blue + static_cast<int>(__redu_num_blue / __redu_steps);")
            lines.append(f"{indent}      {red_var} = __redu_red;")
            lines.append(f"{indent}      {green_var} = __redu_green;")
            lines.append(f"{indent}      {blue_var} = __redu_blue;")
            lines.append(
                f"{indent}      {state_var} = (({red_var} > 0) || ({green_var} > 0) || ({blue_var} > 0));"
            )
            lines.append(f"{indent}      analogWrite({red_pin}, {red_var});")
            lines.append(f"{indent}      analogWrite({green_pin}, {green_var});")
            lines.append(f"{indent}      analogWrite({blue_pin}, {blue_var});")
            lines.append(f"{indent}      if ((__redu_i != __redu_steps) && (__redu_delay_ms > 0UL)) {{")
            lines.append(f"{indent}        delay(__redu_delay_ms);")
            lines.append(f"{indent}      }}")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, RGBLedBlink):
            pin_codes, color_vars, state_var = _ensure_rgb_tracking(node.name)
            red_pin, green_pin, blue_pin = pin_codes
            red_var, green_var, blue_var = color_vars
            red_expr = _emit_expr(node.red)
            green_expr = _emit_expr(node.green)
            blue_expr = _emit_expr(node.blue)
            times_expr = _emit_expr(node.times)
            delay_expr = _emit_expr(node.delay_ms)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  int __redu_times = {times_expr};")
            lines.append(f"{indent}  if (__redu_times < 0) {{ __redu_times = 0; }}")
            lines.append(f"{indent}  long __redu_delay = {delay_expr};")
            lines.append(f"{indent}  if (__redu_delay < 0L) {{ __redu_delay = 0L; }}")
            lines.append(f"{indent}  unsigned long __redu_delay_ms = 0UL;")
            lines.append(f"{indent}  if (__redu_delay > 0L) {{")
            lines.append(f"{indent}    __redu_delay_ms = static_cast<unsigned long>(__redu_delay);")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}  int __redu_original_red = {red_var};")
            lines.append(f"{indent}  int __redu_original_green = {green_var};")
            lines.append(f"{indent}  int __redu_original_blue = {blue_var};")
            lines.append(f"{indent}  bool __redu_original_state = {state_var};")
            lines.append(f"{indent}  int __redu_target_red = {red_expr};")
            lines.append(f"{indent}  if (__redu_target_red < 0) {{ __redu_target_red = 0; }}")
            lines.append(f"{indent}  if (__redu_target_red > 255) {{ __redu_target_red = 255; }}")
            lines.append(f"{indent}  int __redu_target_green = {green_expr};")
            lines.append(f"{indent}  if (__redu_target_green < 0) {{ __redu_target_green = 0; }}")
            lines.append(f"{indent}  if (__redu_target_green > 255) {{ __redu_target_green = 255; }}")
            lines.append(f"{indent}  int __redu_target_blue = {blue_expr};")
            lines.append(f"{indent}  if (__redu_target_blue < 0) {{ __redu_target_blue = 0; }}")
            lines.append(f"{indent}  if (__redu_target_blue > 255) {{ __redu_target_blue = 255; }}")
            lines.append(f"{indent}  for (int __redu_i = 0; __redu_i < __redu_times; ++__redu_i) {{")
            lines.append(f"{indent}    {red_var} = __redu_target_red;")
            lines.append(f"{indent}    {green_var} = __redu_target_green;")
            lines.append(f"{indent}    {blue_var} = __redu_target_blue;")
            lines.append(
                f"{indent}    {state_var} = (({red_var} > 0) || ({green_var} > 0) || ({blue_var} > 0));"
            )
            lines.append(f"{indent}    analogWrite({red_pin}, {red_var});")
            lines.append(f"{indent}    analogWrite({green_pin}, {green_var});")
            lines.append(f"{indent}    analogWrite({blue_pin}, {blue_var});")
            lines.append(f"{indent}    if (__redu_delay_ms > 0UL) {{")
            lines.append(f"{indent}      delay(__redu_delay_ms);")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}    {red_var} = 0;")
            lines.append(f"{indent}    {green_var} = 0;")
            lines.append(f"{indent}    {blue_var} = 0;")
            lines.append(f"{indent}    {state_var} = false;")
            lines.append(f"{indent}    analogWrite({red_pin}, 0);")
            lines.append(f"{indent}    analogWrite({green_pin}, 0);")
            lines.append(f"{indent}    analogWrite({blue_pin}, 0);")
            lines.append(f"{indent}    if (__redu_delay_ms > 0UL) {{")
            lines.append(f"{indent}      delay(__redu_delay_ms);")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}  {red_var} = __redu_original_red;")
            lines.append(f"{indent}  {green_var} = __redu_original_green;")
            lines.append(f"{indent}  {blue_var} = __redu_original_blue;")
            lines.append(f"{indent}  {state_var} = __redu_original_state;")
            lines.append(f"{indent}  analogWrite({red_pin}, {red_var});")
            lines.append(f"{indent}  analogWrite({green_pin}, {green_var});")
            lines.append(f"{indent}  analogWrite({blue_pin}, {blue_var});")
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

        if isinstance(node, BuzzerPlayTone):
            pin_code, state_var, current_var, last_var = _ensure_buzzer_tracking(node.name)
            freq_expr = _emit_expr(node.frequency)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  float __redu_freq = static_cast<float>({freq_expr});")
            lines.append(f"{indent}  if (__redu_freq < 0.0f) {{ __redu_freq = 0.0f; }}")
            lines.append(f"{indent}  if (__redu_freq <= 0.0f) {{")
            lines.append(f"{indent}    {state_var} = false;")
            lines.append(f"{indent}    {current_var} = 0.0f;")
            lines.append(f"{indent}    noTone({pin_code});")
            lines.append(f"{indent}  }} else {{")
            lines.append(f"{indent}    unsigned int __redu_tone = static_cast<unsigned int>(__redu_freq + 0.5f);")
            lines.append(f"{indent}    tone({pin_code}, __redu_tone);")
            lines.append(f"{indent}    {state_var} = true;")
            lines.append(f"{indent}    {current_var} = __redu_freq;")
            lines.append(f"{indent}    {last_var} = __redu_freq;")
            lines.append(f"{indent}  }}")
            if getattr(node, "duration_ms", None) is not None:
                duration_expr = _emit_expr(node.duration_ms) if node.duration_ms is not None else "0"
                lines.append(
                    f"{indent}  unsigned long __redu_duration = static_cast<unsigned long>({duration_expr});"
                )
                lines.append(f"{indent}  if (__redu_duration > 0UL) {{")
                lines.append(f"{indent}    delay(__redu_duration);")
                lines.append(f"{indent}  }}")
                lines.append(f"{indent}  if (__redu_freq > 0.0f) {{")
                lines.append(f"{indent}    noTone({pin_code});")
                lines.append(f"{indent}  }}")
                lines.append(f"{indent}  {state_var} = false;")
                lines.append(f"{indent}  {current_var} = 0.0f;")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, BuzzerStop):
            pin_code, state_var, current_var, _last_var = _ensure_buzzer_tracking(node.name)
            lines.append(f"{indent}{state_var} = false;")
            lines.append(f"{indent}{current_var} = 0.0f;")
            lines.append(f"{indent}noTone({pin_code});")
            continue

        if isinstance(node, BuzzerBeep):
            pin_code, state_var, current_var, last_var = _ensure_buzzer_tracking(node.name)
            lines.append(f"{indent}{{")
            if getattr(node, "frequency", None) is not None:
                freq_expr = _emit_expr(node.frequency) if node.frequency is not None else last_var
                lines.append(f"{indent}  float __redu_freq_target = static_cast<float>({freq_expr});")
            else:
                lines.append(f"{indent}  float __redu_freq_target = {last_var};")
            lines.append(f"{indent}  if (__redu_freq_target < 0.0f) {{ __redu_freq_target = 0.0f; }}")
            lines.append(
                f"{indent}  unsigned long __redu_on_ms = static_cast<unsigned long>({_emit_expr(node.on_ms)});"
            )
            lines.append(
                f"{indent}  unsigned long __redu_off_ms = static_cast<unsigned long>({_emit_expr(node.off_ms)});"
            )
            lines.append(f"{indent}  int __redu_times = static_cast<int>({_emit_expr(node.times)});")
            lines.append(f"{indent}  if (__redu_times < 0) {{ __redu_times = 0; }}")
            lines.append(f"{indent}  for (int __redu_i = 0; __redu_i < __redu_times; ++__redu_i) {{")
            lines.append(f"{indent}    if (__redu_freq_target > 0.0f) {{")
            lines.append(f"{indent}      unsigned int __redu_tone = static_cast<unsigned int>(__redu_freq_target + 0.5f);")
            lines.append(f"{indent}      tone({pin_code}, __redu_tone);")
            lines.append(f"{indent}      {state_var} = true;")
            lines.append(f"{indent}      {current_var} = __redu_freq_target;")
            lines.append(f"{indent}      {last_var} = __redu_freq_target;")
            lines.append(f"{indent}    }} else {{")
            lines.append(f"{indent}      noTone({pin_code});")
            lines.append(f"{indent}      {state_var} = false;")
            lines.append(f"{indent}      {current_var} = 0.0f;")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}    if (__redu_on_ms > 0UL) {{ delay(__redu_on_ms); }}")
            lines.append(f"{indent}    noTone({pin_code});")
            lines.append(f"{indent}    {state_var} = false;")
            lines.append(f"{indent}    {current_var} = 0.0f;")
            lines.append(f"{indent}    if ((__redu_i + 1) < __redu_times && __redu_off_ms > 0UL) {{")
            lines.append(f"{indent}      delay(__redu_off_ms);")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, BuzzerSweep):
            pin_code, state_var, current_var, last_var = _ensure_buzzer_tracking(node.name)
            start_expr = _emit_expr(node.start_hz)
            end_expr = _emit_expr(node.end_hz)
            duration_expr = _emit_expr(node.duration_ms)
            steps_expr = _emit_expr(node.steps)
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  float __redu_start = static_cast<float>({start_expr});")
            lines.append(f"{indent}  if (__redu_start < 0.0f) {{ __redu_start = 0.0f; }}")
            lines.append(f"{indent}  float __redu_end = static_cast<float>({end_expr});")
            lines.append(f"{indent}  if (__redu_end < 0.0f) {{ __redu_end = 0.0f; }}")
            lines.append(f"{indent}  unsigned long __redu_total = static_cast<unsigned long>({duration_expr});")
            lines.append(f"{indent}  int __redu_steps = static_cast<int>({steps_expr});")
            lines.append(f"{indent}  if (__redu_steps < 1) {{ __redu_steps = 1; }}")
            lines.append(
                f"{indent}  float __redu_step_delay = (__redu_steps > 0) ? (static_cast<float>(__redu_total) / static_cast<float>(__redu_steps)) : 0.0f;"
            )
            lines.append(f"{indent}  for (int __redu_i = 0; __redu_i < __redu_steps; ++__redu_i) {{")
            lines.append(
                f"{indent}    float __redu_progress = (__redu_steps == 1) ? 1.0f : (static_cast<float>(__redu_i) / (static_cast<float>(__redu_steps) - 1.0f));"
            )
            lines.append(f"{indent}    float __redu_freq = __redu_start + (__redu_end - __redu_start) * __redu_progress;")
            lines.append(f"{indent}    if (__redu_freq < 0.0f) {{ __redu_freq = 0.0f; }}")
            lines.append(f"{indent}    if (__redu_freq > 0.0f) {{")
            lines.append(f"{indent}      unsigned int __redu_tone = static_cast<unsigned int>(__redu_freq + 0.5f);")
            lines.append(f"{indent}      tone({pin_code}, __redu_tone);")
            lines.append(f"{indent}      {state_var} = true;")
            lines.append(f"{indent}      {current_var} = __redu_freq;")
            lines.append(f"{indent}      {last_var} = __redu_freq;")
            lines.append(f"{indent}    }} else {{")
            lines.append(f"{indent}      noTone({pin_code});")
            lines.append(f"{indent}      {state_var} = false;")
            lines.append(f"{indent}      {current_var} = 0.0f;")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}    if (__redu_step_delay > 0.0f) {{")
            lines.append(f"{indent}      delay(static_cast<unsigned long>(__redu_step_delay));")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}  }}")
            lines.append(f"{indent}  noTone({pin_code});")
            lines.append(f"{indent}  {state_var} = false;")
            lines.append(f"{indent}  {current_var} = 0.0f;")
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, BuzzerMelody):
            pin_code, state_var, current_var, last_var = _ensure_buzzer_tracking(node.name)
            melody_data = _BUZZER_MELODIES.get(node.melody)
            if melody_data is None:
                continue
            default_tempo = melody_data["tempo"]
            tempo_expr = (
                f"static_cast<float>({_emit_expr(node.tempo)})"
                if getattr(node, "tempo", None) is not None
                else _format_float(default_tempo)
            )
            guard_expr = _format_float(default_tempo)
            freqs = ", ".join(_format_float(freq) if freq else "0.0f" for freq, _ in melody_data["sequence"])
            beats = ", ".join(_format_float(beat) for _, beat in melody_data["sequence"])
            lines.append(f"{indent}{{")
            lines.append(f"{indent}  float __redu_tempo = {tempo_expr};")
            lines.append(f"{indent}  if (__redu_tempo <= 0.0f) {{ __redu_tempo = {guard_expr}; }}")
            lines.append(f"{indent}  float __redu_beat_ms = 60000.0f / __redu_tempo;")
            lines.append(f"{indent}  const float __redu_freqs[] = {{{freqs}}};")
            lines.append(f"{indent}  const float __redu_beats[] = {{{beats}}};")
            lines.append(
                f"{indent}  const size_t __redu_melody_len = sizeof(__redu_freqs) / sizeof(__redu_freqs[0]);"
            )
            lines.append(f"{indent}  for (size_t __redu_i = 0; __redu_i < __redu_melody_len; ++__redu_i) {{")
            lines.append(f"{indent}    float __redu_freq = __redu_freqs[__redu_i];")
            lines.append(f"{indent}    float __redu_duration = __redu_beats[__redu_i] * __redu_beat_ms;")
            lines.append(f"{indent}    if (__redu_freq <= 0.0f) {{")
            lines.append(f"{indent}      noTone({pin_code});")
            lines.append(f"{indent}      {state_var} = false;")
            lines.append(f"{indent}      {current_var} = 0.0f;")
            lines.append(f"{indent}      if (__redu_duration > 0.0f) {{ delay(static_cast<unsigned long>(__redu_duration)); }}")
            lines.append(f"{indent}      continue;")
            lines.append(f"{indent}    }}")
            lines.append(f"{indent}    unsigned int __redu_tone = static_cast<unsigned int>(__redu_freq + 0.5f);")
            lines.append(f"{indent}    tone({pin_code}, __redu_tone);")
            lines.append(f"{indent}    {state_var} = true;")
            lines.append(f"{indent}    {current_var} = __redu_freq;")
            lines.append(f"{indent}    {last_var} = __redu_freq;")
            lines.append(f"{indent}    if (__redu_duration > 0.0f) {{ delay(static_cast<unsigned long>(__redu_duration)); }}")
            lines.append(f"{indent}    noTone({pin_code});")
            lines.append(f"{indent}    {state_var} = false;")
            lines.append(f"{indent}    {current_var} = 0.0f;")
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
    buzzer_pin: Dict[str, Union[int, str]] = {}
    buzzer_state: Dict[str, str] = {}
    buzzer_current: Dict[str, str] = {}
    buzzer_last: Dict[str, str] = {}
    rgb_led_pins: Dict[str, Tuple[Union[int, str], Union[int, str], Union[int, str]]] = {}
    rgb_led_state: Dict[str, str] = {}
    rgb_led_colors: Dict[str, Tuple[str, str, str]] = {}
    potentiometer_decls: Dict[str, PotentiometerDecl] = {}
    servo_decls: Dict[str, ServoDecl] = {}
    servo_state: Dict[str, Dict[str, str]] = {}
    servo_attach_emitted: Set[str] = set()
    servo_used = False
    helpers = getattr(ast, "helpers", set())
    ultrasonic_measurements = getattr(ast, "ultrasonic_measurements", set())

    globals_: List[str] = []
    setup_lines: List[str] = []
    loop_lines: List[str] = []

    ultrasonic_decls: Dict[str, UltrasonicDecl] = {}
    ultrasonic_pin_modes: Set[Tuple[str, str, str]] = set()
    loop_ultrasonic_modes: Set[Tuple[str, str, str]] = set()
    button_decls: Dict[str, ButtonDecl] = {}
    button_init_emitted: Set[str] = set()

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
    pin_mode_emitted: Set[Tuple[str, ...]] = set()

    def _ensure_servo_globals(node: ServoDecl) -> Dict[str, str]:
        nonlocal servo_used
        servo_used = True
        info = servo_state.setdefault(
            node.name,
            {
                "object": f"__servo_{node.name}",
                "min_angle": f"__servo_min_angle_{node.name}",
                "max_angle": f"__servo_max_angle_{node.name}",
                "min_pulse": f"__servo_min_pulse_{node.name}",
                "max_pulse": f"__servo_max_pulse_{node.name}",
                "angle": f"__servo_angle_{node.name}",
                "pulse": f"__servo_pulse_{node.name}",
            },
        )
        servo_decls[node.name] = node
        obj_line = f"Servo {info['object']};"
        if obj_line not in globals_:
            globals_.append(obj_line)
        min_angle_expr = _emit_expr(node.min_angle)
        max_angle_expr = _emit_expr(node.max_angle)
        min_pulse_expr = _emit_expr(node.min_pulse_us)
        max_pulse_expr = _emit_expr(node.max_pulse_us)
        min_angle_line = (
            f"float {info['min_angle']} = static_cast<float>({min_angle_expr});"
        )
        if min_angle_line not in globals_:
            globals_.append(min_angle_line)
        max_angle_line = (
            f"float {info['max_angle']} = static_cast<float>({max_angle_expr});"
        )
        if max_angle_line not in globals_:
            globals_.append(max_angle_line)
        min_pulse_line = (
            f"float {info['min_pulse']} = static_cast<float>({min_pulse_expr});"
        )
        if min_pulse_line not in globals_:
            globals_.append(min_pulse_line)
        max_pulse_line = (
            f"float {info['max_pulse']} = static_cast<float>({max_pulse_expr});"
        )
        if max_pulse_line not in globals_:
            globals_.append(max_pulse_line)
        angle_line = f"float {info['angle']} = {info['min_angle']};"
        if angle_line not in globals_:
            globals_.append(angle_line)
        pulse_line = f"float {info['pulse']} = {info['min_pulse']};"
        if pulse_line not in globals_:
            globals_.append(pulse_line)
        return info

    for node in (setup_body or []):
        if isinstance(node, ButtonDecl):
            button_decls[node.name] = node
            prev_var = f"__redu_button_prev_{node.name}"
            value_var = f"__redu_button_value_{node.name}"
            prev_line = f"bool {prev_var} = false;"
            value_line = f"bool {value_var} = false;"
            if prev_line not in globals_:
                globals_.append(prev_line)
            if value_line not in globals_:
                globals_.append(value_line)
            if node.name not in button_init_emitted:
                pin_expr = _emit_expr(node.pin)
                key = (node.name, pin_expr, node.mode)
                if key not in pin_mode_emitted:
                    pin_mode_emitted.add(key)
                    setup_lines.append(f"  pinMode({pin_expr}, {node.mode});")
                setup_lines.append(
                    f"  {prev_var} = (digitalRead({pin_expr}) == HIGH);"
                )
                setup_lines.append(f"  {value_var} = {prev_var};")
                button_init_emitted.add(node.name)
            continue

        if isinstance(node, ServoDecl):
            info = _ensure_servo_globals(node)
            if node.name not in servo_attach_emitted:
                servo_attach_emitted.add(node.name)
                pin_expr = _emit_expr(node.pin)
                min_pulse_expr = _emit_expr(node.min_pulse_us)
                max_pulse_expr = _emit_expr(node.max_pulse_us)
                setup_lines.append(
                    f"  {info['object']}.attach({pin_expr}, static_cast<int>({min_pulse_expr}), static_cast<int>({max_pulse_expr}));"
                )
                setup_lines.append(
                    f"  {info['object']}.writeMicroseconds(static_cast<int>({min_pulse_expr}));"
                )
            continue

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
        if isinstance(node, BuzzerDecl):
            buzzer_pin[node.name] = node.pin
            state_var = f"__buzzer_state_{node.name}"
            current_var = f"__buzzer_current_{node.name}"
            last_var = f"__buzzer_last_{node.name}"
            buzzer_state[node.name] = state_var
            buzzer_current[node.name] = current_var
            buzzer_last[node.name] = last_var
            state_line = f"bool {state_var} = false;"
            if state_line not in globals_:
                globals_.append(state_line)
            current_line = f"float {current_var} = 0.0f;"
            if current_line not in globals_:
                globals_.append(current_line)
            default_expr = _emit_expr(node.default_frequency)
            last_line = f"float {last_var} = static_cast<float>({default_expr});"
            if last_line not in globals_:
                globals_.append(last_line)
            pin_expr = _emit_expr(node.pin)
            key = (node.name, pin_expr, "OUTPUT")
            if key not in pin_mode_emitted:
                pin_mode_emitted.add(key)
                setup_lines.append(f"  pinMode({pin_expr}, OUTPUT);")
        if isinstance(node, RGBLedDecl):
            state_var = f"__rgb_state_{node.name}"
            color_vars = (
                f"__rgb_red_{node.name}",
                f"__rgb_green_{node.name}",
                f"__rgb_blue_{node.name}",
            )
            rgb_led_state[node.name] = state_var
            rgb_led_colors[node.name] = color_vars
            state_line = f"bool {state_var} = false;"
            if state_line not in globals_:
                globals_.append(state_line)
            for var in color_vars:
                color_line = f"int {var} = 0;"
                if color_line not in globals_:
                    globals_.append(color_line)
            rgb_led_pins[node.name] = (node.red_pin, node.green_pin, node.blue_pin)
        if isinstance(node, UltrasonicDecl):
            ultrasonic_decls[node.name] = node
        if isinstance(node, PotentiometerDecl):
            potentiometer_decls[node.name] = node
            pin_expr = _emit_expr(node.pin)
            key = (node.name, pin_expr, "INPUT")
            if key not in pin_mode_emitted:
                pin_mode_emitted.add(key)
                setup_lines.append(f"  pinMode({pin_expr}, INPUT);")

    for node in (loop_body or []):
        if isinstance(node, ButtonDecl):
            button_decls[node.name] = node
            prev_var = f"__redu_button_prev_{node.name}"
            value_var = f"__redu_button_value_{node.name}"
            prev_line = f"bool {prev_var} = false;"
            value_line = f"bool {value_var} = false;"
            if prev_line not in globals_:
                globals_.append(prev_line)
            if value_line not in globals_:
                globals_.append(value_line)
            pin_expr = _emit_expr(node.pin)
            key = (node.name, pin_expr, node.mode)
            if key not in pin_mode_emitted:
                pin_mode_emitted.add(key)
                setup_lines.append(f"  pinMode({pin_expr}, {node.mode});")
            continue

        if isinstance(node, ServoDecl):
            info = _ensure_servo_globals(node)
            if node.name not in servo_attach_emitted:
                servo_attach_emitted.add(node.name)
                pin_expr = _emit_expr(node.pin)
                min_pulse_expr = _emit_expr(node.min_pulse_us)
                max_pulse_expr = _emit_expr(node.max_pulse_us)
                setup_lines.append(
                    f"  {info['object']}.attach({pin_expr}, static_cast<int>({min_pulse_expr}), static_cast<int>({max_pulse_expr}));"
                )
                setup_lines.append(
                    f"  {info['object']}.writeMicroseconds(static_cast<int>({min_pulse_expr}));"
                )
            continue

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
        if isinstance(node, RGBLedDecl):
            state_var = f"__rgb_state_{node.name}"
            color_vars = (
                f"__rgb_red_{node.name}",
                f"__rgb_green_{node.name}",
                f"__rgb_blue_{node.name}",
            )
            if node.name not in rgb_led_state:
                rgb_led_state[node.name] = state_var
                state_line = f"bool {state_var} = false;"
                if state_line not in globals_:
                    globals_.append(state_line)
            if node.name not in rgb_led_colors:
                rgb_led_colors[node.name] = color_vars
                for var in color_vars:
                    color_line = f"int {var} = 0;"
                    if color_line not in globals_:
                        globals_.append(color_line)
            else:
                # Ensure globals exist even if tuple already recorded
                for var in rgb_led_colors[node.name]:
                    color_line = f"int {var} = 0;"
                    if color_line not in globals_:
                        globals_.append(color_line)
            rgb_led_pins.setdefault(
                node.name, (node.red_pin, node.green_pin, node.blue_pin)
            )
            for idx, pin in enumerate((node.red_pin, node.green_pin, node.blue_pin)):
                pin_expr = _emit_expr(pin)
                key = (node.name, pin_expr, str(idx))
                if key not in pin_mode_emitted:
                    pin_mode_emitted.add(key)
                    setup_lines.append(f"  pinMode({pin_expr}, OUTPUT);")
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
        if isinstance(node, PotentiometerDecl):
            potentiometer_decls.setdefault(node.name, node)
            pin_expr = _emit_expr(node.pin)
            key = (node.name, pin_expr, "INPUT")
            if key not in pin_mode_emitted:
                pin_mode_emitted.add(key)
                setup_lines.append(f"  pinMode({pin_expr}, INPUT);")

    # Pass 2: emit statements
    setup_lines.extend(
        _emit_block(
            setup_body or [],
            led_pin,
            led_state,
            led_brightness,
            buzzer_pin,
            buzzer_state,
            buzzer_current,
            buzzer_last,
            rgb_led_pins,
            rgb_led_state,
            rgb_led_colors,
            ultrasonic_decls,
            potentiometer_decls,
            button_decls,
            servo_decls,
            servo_state,
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
                    buzzer_pin,
                    buzzer_state,
                    buzzer_current,
                    buzzer_last,
                    rgb_led_pins,
                    rgb_led_state,
                    rgb_led_colors,
                    ultrasonic_decls,
                    potentiometer_decls,
                    button_decls,
                    servo_decls,
                    servo_state,
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
            buzzer_pin,
            buzzer_state,
            buzzer_current,
            buzzer_last,
            rgb_led_pins,
            rgb_led_state,
            rgb_led_colors,
            ultrasonic_decls,
            potentiometer_decls,
            button_decls,
            servo_decls,
            servo_state,
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
            dict(buzzer_pin),
            dict(buzzer_state),
            dict(buzzer_current),
            dict(buzzer_last),
            dict(rgb_led_pins),
            dict(rgb_led_state),
            dict(rgb_led_colors),
            ultrasonic_decls,
            potentiometer_decls,
            button_decls,
            servo_decls,
            servo_state,
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
            f"  static unsigned long __redu_last_trigger_ms_{name} = 0UL;",
            f"  static float __redu_last_distance_{name} = 400.0f;",
            f"  static bool __redu_has_distance_{name} = false;",
            f"  const unsigned long __redu_min_interval_ms_{name} = 60UL;",
            f"  const unsigned int __redu_max_attempts_{name} = 3U;",
            f"  for (unsigned int __redu_attempt_{name} = 0U; __redu_attempt_{name} < __redu_max_attempts_{name}; ++__redu_attempt_{name}) {{",
            f"    unsigned long __redu_now_ms_{name} = millis();",
            f"    if (__redu_last_trigger_ms_{name} != 0UL) {{",
            f"      unsigned long __redu_elapsed_ms_{name} = __redu_now_ms_{name} - __redu_last_trigger_ms_{name};",
            f"      if (__redu_elapsed_ms_{name} < __redu_min_interval_ms_{name}) {{",
            f"        delay(__redu_min_interval_ms_{name} - __redu_elapsed_ms_{name});",
            f"        __redu_now_ms_{name} = millis();",
            "      }",
            "    }",
            f"    digitalWrite({trig_expr}, LOW);",
            "    delayMicroseconds(2);",
            f"    digitalWrite({trig_expr}, HIGH);",
            "    delayMicroseconds(10);",
            f"    digitalWrite({trig_expr}, LOW);",
            f"    unsigned long __redu_duration_{name} = pulseIn({echo_expr}, HIGH, 30000UL);",
            f"    __redu_last_trigger_ms_{name} = millis();",
            f"    if (__redu_duration_{name} > 0UL) {{",
            f"      float __redu_distance_{name} = (static_cast<float>(__redu_duration_{name}) * 0.0343f) / 2.0f;",
            f"      __redu_last_distance_{name} = __redu_distance_{name};",
            f"      __redu_has_distance_{name} = true;",
            f"      return __redu_distance_{name};",
            "    }",
            "  }",
            f"  if (__redu_has_distance_{name}) {{",
            f"    return __redu_last_distance_{name};",
            "  }",
            "  return 400.0f;",
            "}\n",
        ]
        ultrasonic_sections.append("\n".join(helper_lines))

    # Stitch sections
    parts: List[str] = [HEADER]
    if servo_used:
        parts.append("#include <Servo.h>\n\n")
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
