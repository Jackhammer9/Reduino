"""Parse the Reduino DSL into the internal abstract syntax tree."""

from __future__ import annotations

import ast
import operator as op
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .ast import (
    BreakStmt,
    ButtonDecl,
    ButtonPoll,
    CatchClause,
    ConditionalBranch,
    ExprStmt,
    ForRangeLoop,
    FunctionDef,
    BuzzerBeep,
    BuzzerDecl,
    BuzzerMelody,
    BuzzerPlayTone,
    BuzzerStop,
    BuzzerSweep,
    LCDAnimate,
    LCDBacklight,
    LCDBrightness,
    LCDClear,
    LCDDecl,
    LCDDisplay,
    LCDGlyph,
    LCDLine,
    LCDMessage,
    LCDProgress,
    LCDTick,
    LCDWrite,
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
    RGBLedBlink,
    RGBLedDecl,
    RGBLedFade,
    RGBLedOff,
    RGBLedOn,
    RGBLedSetColor,
    ServoDecl,
    ServoWrite,
    ServoWriteMicroseconds,
    Program,
    ReturnStmt,
    SerialMonitorDecl,
    SerialWrite,
    Sleep,
    TryStatement,
    UltrasonicDecl,
    VarAssign,
    VarDecl,
    WhileLoop,
    PotentiometerDecl,
)

_BIN = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "/",
    ast.Mod: "%", ast.Pow: "**", ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^",
    ast.LShift: "<<", ast.RShift: ">>",
}
_UN = {ast.UAdd: "+", ast.USub: "-", ast.Not: "!"}
_CMP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

ANALOG_PIN_RE = re.compile(r"^A\d+$")


def _escape_string_literal(value: str) -> str:
    """Escape a Python string literal into a C/C++ literal body."""

    return value.replace("\\", "\\\\").replace('"', '\\"')


class _ExprStr(str):
    """Marker subclass used to flag unresolved expression fragments."""


_SAFE_CASTS = {
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
}

_SAFE_NAME_REFERENCES = {"len", "abs", "max", "min", "int", "float", "bool", "str"}


def _make_list_type_label(element_type: str) -> str:
    """Return the canonical internal type label for a list of ``element_type``."""

    return f"list[{element_type}]"


def _is_list_type(label: str) -> bool:
    """Return ``True`` if ``label`` represents a list type."""

    return isinstance(label, str) and label.startswith("list[") and label.endswith("]")


def _list_element_type(label: str) -> str:
    """Extract the contained element type label from a list ``label``."""

    if not _is_list_type(label):
        return "int"
    return label[5:-1]


def _merge_element_types(types: List[str]) -> str:
    """Merge element type labels used inside a list literal/comprehension."""

    if not types:
        return "int"
    # Uniform element type → preserve it directly
    unique = list(dict.fromkeys(types))
    if len(unique) == 1:
        return unique[0]

    # Nested lists must all share the same signature
    list_types = [t for t in unique if _is_list_type(t)]
    if list_types:
        if len(list_types) != len(unique):
            raise ValueError("mixed list and scalar element types")
        if len(set(list_types)) != 1:
            raise ValueError("conflicting nested list element types")
        return list_types[0]

    if "String" in unique:
        return "String"
    if "float" in unique:
        return "float"
    if "int" in unique:
        return "int"
    if "bool" in unique:
        return "bool"
    return unique[0]

_BUILTIN_CALL_RETURN_TYPES = {
    "int": "int",
    "float": "float",
    "bool": "bool",
    "str": "String",
    "len": "int",
    "abs": "int",
    "max": "int",
    "min": "int",
}

def _eval_const(expr: str, env: dict):
    """Evaluate a safe subset of Python expr to a constant using env (ints/floats/str)."""

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, str, bool)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in env:
                val = env[n.id]
                if isinstance(val, _ExprStr):
                    raise ValueError("non-const name")
                if isinstance(val, (int, float, str, bool)):
                    return val
            raise ValueError("non-const name")
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return _apply_bin(type(n.op), ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UN:
            v = ev(n.operand)
            if isinstance(n.op, ast.UAdd):
                return v
            if isinstance(n.op, ast.USub):
                return -v
            if isinstance(n.op, ast.Not):
                return not v
        if isinstance(n, ast.BoolOp):
            if isinstance(n.op, ast.And):
                result = True
                for value in n.values:
                    result = result and ev(value)
                return result
            if isinstance(n.op, ast.Or):
                result = False
                for value in n.values:
                    result = result or ev(value)
                return result

        if isinstance(n, ast.Compare):
            if not n.ops:
                raise ValueError("unsupported")
            left_val = ev(n.left)
            for op_node, comp in zip(n.ops, n.comparators):
                right_val = ev(comp)
                ops = {
                    ast.Eq: op.eq,
                    ast.NotEq: op.ne,
                    ast.Lt: op.lt,
                    ast.LtE: op.le,
                    ast.Gt: op.gt,
                    ast.GtE: op.ge,
                }
                func = ops.get(type(op_node))
                if func is None:
                    raise ValueError("unsupported")
                if not func(left_val, right_val):
                    return False
                left_val = right_val
            return True

        if isinstance(n, ast.IfExp):
            cond = ev(n.test)
            branch = n.body if cond else n.orelse
            return ev(branch)

        if isinstance(n, ast.JoinedStr):
            parts: List[str] = []
            for value in n.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                    continue
                if isinstance(value, ast.FormattedValue):
                    if value.conversion not in (-1, None):
                        raise ValueError("unsupported conversion")
                    if value.format_spec is not None:
                        raise ValueError("unsupported format spec")
                    parts.append(str(ev(value.value)))
                    continue
                raise ValueError("unsupported f-string")
            return "".join(parts)
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in _SAFE_CASTS
            and len(n.args) == 1
            and not n.keywords
        ):
            inner = ev(n.args[0])
            try:
                return _SAFE_CASTS[n.func.id](inner)
            except Exception as exc:  # pragma: no cover - defensive guard
                raise ValueError("cast failed") from exc
            
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "len"
            and len(n.args) == 1
            and not n.keywords
        ):
            inner = ev(n.args[0])

            if isinstance(inner, (str, tuple, list)):
                return len(inner)
            raise ValueError("len() on non-constant")

        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "abs"
            and len(n.args) == 1
            and not n.keywords
        ):
            inner = ev(n.args[0])

            if isinstance(inner, (int, float)):
                return abs(inner)
            raise ValueError("abs() on non-numeric or non-constant")

        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "max"
            and len(n.args) >= 1
            and not n.keywords
        ):

            return max(ev(arg) for arg in n.args)

        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "min"
            and len(n.args) >= 1
            and not n.keywords
        ):

            return min(ev(arg) for arg in n.args)
        
        if isinstance(n, (ast.Tuple, ast.List)):
            values = [ev(elt) for elt in n.elts]
            return values if isinstance(n, ast.List) else tuple(values)

        raise ValueError("unsupported")

    def _apply_bin(opcls, a, b):
        if opcls is ast.Add and isinstance(a, str) and isinstance(b, str):
            return a + b
        ops = {
            ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
            ast.FloorDiv: op.floordiv, ast.Mod: op.mod, ast.Pow: op.pow,
            ast.BitAnd: op.and_, ast.BitOr: op.or_, ast.BitXor: op.xor,
            ast.LShift: op.lshift, ast.RShift: op.rshift,
        }
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            raise ValueError("unsupported operand type")
        return ops[opcls](a, b)

    tree = ast.parse(expr, mode="eval")
    return ev(tree.body)


def _to_c_expr(
    expr: str, env: dict, ctx: Optional[Dict[str, object]] = None
) -> str:
    """Emit a C-like expression string from a safe Python expr; substitute known consts."""

    helper_set: Optional[Set[str]] = None
    vars_env: Dict[str, object] = env if isinstance(env, dict) else {}
    if isinstance(env, dict):
        helpers = env.get("_helpers")
        if isinstance(helpers, set):
            helper_set = helpers
        if ctx is None:
            ctx = env.get("_ctx") if isinstance(env.get("_ctx"), dict) else None

    def _mark_helper(name: str) -> None:
        if helper_set is not None:
            helper_set.add(name)

    def _infer_arg_type(node: ast.AST) -> Optional[str]:
        if ctx is None:
            return None
        return _infer_expr_type(
            node,
            ctx.get("var_types", {}),
            ctx.get("functions", {}),
            ctx.get("function_param_types", {}),
            ctx.get("function_param_orders", {}),
            ctx,
        )

    def _literal_length(node: ast.AST) -> Optional[int]:
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, (str, tuple, list)):
                return len(value)
            return None
        if isinstance(node, (ast.Tuple, ast.List)):
            return len(node.elts)
        if isinstance(node, ast.Name) and isinstance(env, dict):
            bound = env.get(node.id)
            if isinstance(bound, _ExprStr):
                return None
            if isinstance(bound, (str, tuple, list)):
                return len(bound)
        return None

    def emit(n: ast.AST) -> str:
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool):
                return "true" if n.value else "false"
            if isinstance(n.value, (int, float)):
                return str(int(n.value)) if isinstance(n.value, int) else str(n.value)
            if isinstance(n.value, str):
                return f'"{_escape_string_literal(n.value)}"'

        if isinstance(n, ast.Name):
            return n.id

        if isinstance(n, ast.Subscript):
            if ctx is None:
                raise ValueError("subscript requires context")
            base = emit(n.value)
            if isinstance(n.slice, ast.Slice):
                raise ValueError("slices are unsupported")
            if hasattr(ast, "Index") and isinstance(n.slice, ast.Index):  # type: ignore[attr-defined]
                index_node = n.slice.value
            else:
                index_node = n.slice
            index_expr = emit(index_node)
            base_type = _infer_expr_type(
                n.value,
                ctx.get("var_types", {}),
                ctx.get("functions", {}),
                ctx.get("function_param_types", {}),
                ctx.get("function_param_orders", {}),
                ctx,
            )
            if _is_list_type(base_type):
                _mark_helper("list")
                return f"__redu_list_get({base}, {index_expr})"
            return f"{base}[{index_expr}]"

        if isinstance(n, ast.List):
            if ctx is None:
                raise ValueError("list literal requires context")
            _mark_helper("list")
            items = [emit(elt) for elt in n.elts]
            elem_label = _list_element_type(
                _infer_expr_type(
                    n,
                    ctx.get("var_types", {}),
                    ctx.get("functions", {}),
                    ctx.get("function_param_types", {}),
                    ctx.get("function_param_orders", {}),
                    ctx,
                )
            )
            elem_cpp = _cpp_type(elem_label)
            if not items:
                return f"__redu_make_list<{elem_cpp}>()"
            joined = ", ".join(items)
            return f"__redu_make_list<{elem_cpp}>({joined})"

        if isinstance(n, ast.ListComp):
            if ctx is None:
                raise ValueError("list comprehension requires context")
            if len(n.generators) != 1:
                raise ValueError("only single generator comprehensions supported")
            comp = n.generators[0]
            if comp.ifs:
                raise ValueError("filtered comprehensions unsupported")
            if not isinstance(comp.target, ast.Name):
                raise ValueError("comprehension target must be a simple name")
            if not (
                isinstance(comp.iter, ast.Call)
                and isinstance(comp.iter.func, ast.Name)
                and comp.iter.func.id == "range"
            ):
                raise ValueError("only range() comprehensions supported")
            range_args = comp.iter.args
            if not 1 <= len(range_args) <= 3 or comp.iter.keywords:
                raise ValueError("unsupported range() form in comprehension")

            start_expr = "0"
            stop_expr = emit(range_args[0]) if range_args else "0"
            step_expr = "1"
            if len(range_args) >= 2:
                start_expr = emit(range_args[0])
                stop_expr = emit(range_args[1])
            if len(range_args) == 3:
                step_expr = emit(range_args[2])

            loop_name = comp.target.id
            saved_env = vars_env.get(loop_name)
            vars_env[loop_name] = _ExprStr(loop_name)
            var_types_ctx = ctx.setdefault("var_types", {})
            saved_type = var_types_ctx.get(loop_name)
            var_types_ctx[loop_name] = "int"
            try:
                body_expr = emit(n.elt)
            finally:
                if saved_env is None:
                    vars_env.pop(loop_name, None)
                else:
                    vars_env[loop_name] = saved_env
                if saved_type is None:
                    var_types_ctx.pop(loop_name, None)
                else:
                    var_types_ctx[loop_name] = saved_type

            elem_label = _list_element_type(
                _infer_expr_type(
                    n,
                    ctx.get("var_types", {}),
                    ctx.get("functions", {}),
                    ctx.get("function_param_types", {}),
                    ctx.get("function_param_orders", {}),
                    ctx,
                )
            )
            elem_cpp = _cpp_type(elem_label)
            _mark_helper("list")
            return (
                f"__redu_list_from_range<{elem_cpp}>({start_expr}, {stop_expr}, {step_expr}, "
                f"[&](int {loop_name}) {{ return {body_expr}; }})"
            )

        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return f"({emit(n.left)} {_BIN[type(n.op)]} {emit(n.right)})"

        if isinstance(n, ast.UnaryOp) and type(n.op) in _UN:
            op_token = _UN[type(n.op)]
            return f"({op_token}{emit(n.operand)})"

        if isinstance(n, ast.BoolOp):
            op_token = "&&" if isinstance(n.op, ast.And) else "||"
            return "(" + f" {op_token} ".join(emit(v) for v in n.values) + ")"

        if isinstance(n, ast.Compare):
            parts = []
            left = emit(n.left)
            for op_node, comparator in zip(n.ops, n.comparators):
                op_token = _CMP.get(type(op_node))
                if op_token is None:
                    raise ValueError("unsupported")
                right = emit(comparator)
                parts.append(f"{left} {op_token} {right}")
                left = right
            return "(" + " && ".join(parts) + ")"

        if isinstance(n, ast.IfExp):
            return (
                f"({emit(n.test)} ? {emit(n.body)} : {emit(n.orelse)})"
            )

        if isinstance(n, ast.JoinedStr):
            has_formatted = any(isinstance(v, ast.FormattedValue) for v in n.values)
            if not has_formatted:
                literal = "".join(
                    v.value for v in n.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
                return f'"{_escape_string_literal(literal)}"'

            expr: Optional[str] = None
            for value in n.values:
                if isinstance(value, ast.Constant):
                    if not isinstance(value.value, str):
                        raise ValueError("unsupported f-string component")
                    if not value.value:
                        continue
                    literal = f'"{_escape_string_literal(value.value)}"'
                    if expr is None:
                        expr = f"String({literal})"
                    else:
                        expr = f"({expr} + {literal})"
                    continue
                if isinstance(value, ast.FormattedValue):
                    if value.conversion not in (-1, None):
                        raise ValueError("unsupported f-string conversion")
                    if value.format_spec is not None:
                        raise ValueError("unsupported f-string format spec")
                    formatted = f"String({emit(value.value)})"
                    if expr is None:
                        expr = formatted
                    else:
                        expr = f"({expr} + {formatted})"
                    continue
                raise ValueError("unsupported f-string component")

            return expr or '""'

        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            attr = n.func.attr
            owner_node = n.func.value
            owner = emit(owner_node)

            if attr in {"append", "remove"}:
                if len(n.args) != 1 or n.keywords:
                    raise ValueError("unsupported list method usage")
                _mark_helper("list")
                arg_expr = emit(n.args[0])
                helper = "__redu_list_append" if attr == "append" else "__redu_list_remove"
                return f"{helper}({owner}, {arg_expr})"

            if attr == "get_state":
                if n.args or n.keywords:
                    raise ValueError("unsupported attribute call")
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    led_names = ctx.get("led_names", set())
                    if owner_node.id in led_names:
                        return f"__state_{owner_node.id}"
                    buzzer_names = ctx.get("buzzer_names", set())
                    if owner_node.id in buzzer_names:
                        return f"__buzzer_state_{owner_node.id}"
                raise ValueError("unsupported attribute call")

            if attr == "get_brightness":
                if n.args or n.keywords:
                    raise ValueError("unsupported attribute call")
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    led_names = ctx.get("led_names", set())
                    if owner_node.id in led_names:
                        return f"__brightness_{owner_node.id}"
                raise ValueError("unsupported attribute call")

            if attr == "get_frequency":
                if n.args or n.keywords:
                    raise ValueError("unsupported attribute call")
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    buzzer_names = ctx.get("buzzer_names", set())
                    if owner_node.id in buzzer_names:
                        return f"__buzzer_current_{owner_node.id}"
                raise ValueError("unsupported attribute call")

            if attr == "get_last_frequency":
                if n.args or n.keywords:
                    raise ValueError("unsupported attribute call")
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    buzzer_names = ctx.get("buzzer_names", set())
                    if owner_node.id in buzzer_names:
                        return f"__buzzer_last_{owner_node.id}"
                raise ValueError("unsupported attribute call")

            if attr == "measure_distance":
                if n.args or n.keywords:
                    raise ValueError("unsupported attribute call")
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    sensors = ctx.get("ultrasonic_names", set())
                    if owner_node.id in sensors:
                        measure_calls: Set[str] = ctx.setdefault(
                            "ultrasonic_measure_calls", set()
                        )
                        measure_calls.add(owner_node.id)
                        return f"__redu_ultrasonic_measure_{owner_node.id}()"
                raise ValueError("unsupported attribute call")

            if attr == "is_pressed":
                if n.args or n.keywords:
                    raise ValueError("unsupported attribute call")
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    buttons = ctx.get("button_names", set())
                    if owner_node.id in buttons:
                        poll_names: Set[str] = ctx.setdefault(
                            "button_poll_names", set()
                        )
                        poll_names.add(owner_node.id)
                        ctx["button_force_loop"] = True
                        return f"(__redu_button_value_{owner_node.id} ? 1 : 0)"
                raise ValueError("unsupported attribute call")

            if attr == "read":
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    servo_names = ctx.get("servo_names", set())
                    if owner_node.id in servo_names:
                        if n.args or n.keywords:
                            raise ValueError("unsupported attribute call")
                        return f"__servo_angle_{owner_node.id}"
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    potentiometers = ctx.get("potentiometer_names", set())
                    if owner_node.id in potentiometers:
                        if n.args or n.keywords:
                            raise ValueError("unsupported attribute call")
                        pins = ctx.get("potentiometer_pins", {})
                        pin_value = pins.get(owner_node.id)
                        if pin_value is None:
                            raise ValueError("unsupported attribute call")
                        return f"analogRead({pin_value})"

                emit_mode = "both"

                if n.args:
                    if len(n.args) != 1 or n.keywords:
                        raise ValueError("unsupported attribute call")
                    arg = n.args[0]
                    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                        raise ValueError("unsupported attribute call")
                    emit_mode = arg.value
                elif n.keywords:
                    if len(n.keywords) != 1:
                        raise ValueError("unsupported attribute call")
                    keyword = n.keywords[0]
                    if keyword.arg != "emit":
                        raise ValueError("unsupported attribute call")
                    if not isinstance(keyword.value, ast.Constant) or not isinstance(keyword.value.value, str):
                        raise ValueError("unsupported attribute call")
                    emit_mode = keyword.value.value

                if emit_mode not in {"host", "mcu", "both"}:
                    raise ValueError("unsupported attribute call")

                if isinstance(owner_node, ast.Name) and ctx is not None:
                    serials = ctx.get("serial_monitors", set())
                    if owner_node.id in serials:
                        if emit_mode in {"both", "mcu"}:
                            return "Serial.readStringUntil('\\n')"
                        return ''
                raise ValueError("unsupported attribute call")

            if attr == "read_us":
                if isinstance(owner_node, ast.Name) and ctx is not None:
                    servo_names = ctx.get("servo_names", set())
                    if owner_node.id in servo_names:
                        if n.args or n.keywords:
                            raise ValueError("unsupported attribute call")
                        return f"__servo_pulse_{owner_node.id}"
                raise ValueError("unsupported attribute call")

            raise ValueError("unsupported attribute call")

        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            fname = n.func.id
            if fname == "str" and len(n.args) == 1 and not n.keywords:
                return f"String({emit(n.args[0])})"
            if fname in {"int", "float"} and len(n.args) == 1 and not n.keywords:
                arg = n.args[0]
                arg_expr = emit(arg)
                arg_type = _infer_arg_type(arg)
                if arg_type == "String":
                    if arg_expr.startswith('"'):
                        base = f"String({arg_expr})"
                        return f"{base}.to{fname.capitalize()}()"
                    return f"({arg_expr}).to{fname.capitalize()}()"
                return f"static_cast<{fname}>({arg_expr})"
            if fname == "bool" and len(n.args) == 1 and not n.keywords:
                return f"static_cast<bool>({emit(n.args[0])})"
            if fname == "len" and len(n.args) == 1 and not n.keywords:
                literal_len = _literal_length(n.args[0])
                if literal_len is not None:
                    return str(literal_len)
                _mark_helper("len")
                return f"static_cast<int>(__redu_len({emit(n.args[0])}))"
            if fname == "abs" and len(n.args) == 1 and not n.keywords:
                return f"abs({emit(n.args[0])})"
            if fname in {"max", "min"} and len(n.args) >= 1 and not n.keywords:
                if len(n.args) == 1:
                    return emit(n.args[0])

                def _fold(exprs: List[str]) -> str:
                    acc = exprs[0]
                    for sub in exprs[1:]:
                        acc = f"{fname}({acc}, {sub})"
                    return acc

                return _fold([emit(arg) for arg in n.args])
            if n.keywords:
                raise ValueError("unsupported keyword arguments in call")
            args_rendered = ", ".join(emit(arg) for arg in n.args)
            return f"{fname}({args_rendered})"

        raise ValueError("unsupported")

    tree = ast.parse(expr, mode="eval")
    return emit(tree.body)


def _resolve_signature_alias(
    name: str,
    signature: Tuple[str, ...],
    ctx: Dict[str, object],
) -> Tuple[str, ...]:
    """Return the canonical signature for ``name`` and ``signature`` if one exists."""

    aliases: Dict[str, Dict[Tuple[str, ...], Tuple[str, ...]]] = ctx.get(
        "function_signature_aliases", {}
    )
    return aliases.get(name, {}).get(signature, signature)


def _ensure_function_variant(
    name: str,
    signature: Tuple[str, ...],
    ctx: Dict[str, object],
) -> Optional[FunctionDef]:
    """Ensure that ``name`` has a helper variant compatible with ``signature``."""

    defs: Dict[str, Dict[Tuple[str, ...], FunctionDef]] = ctx.setdefault(
        "function_defs", {}
    )
    canonical = _resolve_signature_alias(name, signature, ctx)
    if name in defs and canonical in defs[name]:
        return defs[name][canonical]

    sources: Dict[str, Tuple[str, List[str]]] = ctx.get("function_sources", {})
    if name not in sources:
        return None

    refreshing: Set[Tuple[str, Tuple[str, ...]]] = ctx.setdefault(
        "_refreshing_functions", set()
    )
    key = (name, signature)
    if key in refreshing:
        return defs.get(name, {}).get(canonical)

    refreshing.add(key)
    try:
        params_src, block = sources[name]
        _parse_function(name, params_src, list(block), ctx, forced_signature=signature)
    finally:
        refreshing.remove(key)

    defs = ctx.get("function_defs", {})
    canonical = _resolve_signature_alias(name, signature, ctx)
    return defs.get(name, {}).get(canonical)


def _infer_expr_type(
    node: ast.AST,
    var_types: Dict[str, str],
    functions: Optional[Dict[str, Dict[Tuple[str, ...], str]]] = None,
    function_param_types: Optional[Dict[str, Dict[int, str]]] = None,
    function_param_orders: Optional[Dict[str, List[str]]] = None,
    ctx: Optional[Dict[str, object]] = None,
) -> str:
    """Infer a coarse C++ type for the provided AST expression."""

    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "String"
        return "int"

    if isinstance(node, ast.Name):
        return var_types.get(node.id, "int")

    if isinstance(node, ast.Subscript):
        base_type = _infer_expr_type(
            node.value,
            var_types,
            functions,
            function_param_types,
            function_param_orders,
            ctx,
        )
        if _is_list_type(base_type):
            return _list_element_type(base_type)
        return "int"

    if isinstance(node, ast.List):
        elem_types = [
            _infer_expr_type(
                elt,
                var_types,
                functions,
                function_param_types,
                function_param_orders,
                ctx,
            )
            for elt in node.elts
        ]
        element_type = _merge_element_types(elem_types)
        return _make_list_type_label(element_type)

    if isinstance(node, ast.ListComp):
        if len(node.generators) != 1:
            raise ValueError("unsupported list comprehension form")
        comp = node.generators[0]
        if comp.ifs:
            raise ValueError("unsupported filtered list comprehension")
        if not isinstance(comp.target, ast.Name):
            raise ValueError("unsupported comprehension target")
        if not (
            isinstance(comp.iter, ast.Call)
            and isinstance(comp.iter.func, ast.Name)
            and comp.iter.func.id == "range"
        ):
            raise ValueError("unsupported comprehension iterator")
        loop_name = comp.target.id
        saved_type = var_types.get(loop_name)
        var_types[loop_name] = "int"
        try:
            element_type = _infer_expr_type(
                node.elt,
                var_types,
                functions,
                function_param_types,
                function_param_orders,
                ctx,
            )
        finally:
            if saved_type is None:
                var_types.pop(loop_name, None)
            else:
                var_types[loop_name] = saved_type
        return _make_list_type_label(element_type)

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return "bool"
        return _infer_expr_type(
            node.operand,
            var_types,
            functions,
            function_param_types,
            function_param_orders,
            ctx,
        )

    if isinstance(node, ast.BoolOp):
        return "bool"

    if isinstance(node, ast.Compare):
        return "bool"

    if isinstance(node, ast.IfExp):
        body_type = _infer_expr_type(
            node.body,
            var_types,
            functions,
            function_param_types,
            function_param_orders,
            ctx,
        )
        else_type = _infer_expr_type(
            node.orelse,
            var_types,
            functions,
            function_param_types,
            function_param_orders,
            ctx,
        )
        if body_type == else_type:
            return body_type
        if "String" in (body_type, else_type):
            return "String"
        if "float" in (body_type, else_type):
            return "float"
        return "int"

    if isinstance(node, ast.JoinedStr):
        return "String"

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        attr = node.func.attr
        owner = node.func.value
        if attr == "get_state" and isinstance(owner, ast.Name):
            if ctx is None:
                return "bool"
            led_names = ctx.get("led_names", set())
            if owner.id in led_names:
                return "bool"
            
        if attr == "get_brightness" and isinstance(owner, ast.Name):
            if ctx is None:
                return "int"
            led_names = ctx.get("led_names", set())
            if owner.id in led_names:
                return "int"

        if attr == "read" and isinstance(owner, ast.Name):
            if ctx is None:
                return "float"
            servo_names = ctx.get("servo_names", set())
            if owner.id in servo_names:
                return "float"
            if ctx is None:
                return "String"
            serials = ctx.get("serial_monitors", set())
            if owner.id in serials:
                return "String"

        if attr == "read_us" and isinstance(owner, ast.Name):
            if ctx is None:
                return "float"
            servo_names = ctx.get("servo_names", set())
            if owner.id in servo_names:
                return "float"

        if attr == "measure_distance" and isinstance(owner, ast.Name):
            if ctx is None:
                return "float"
            sensors = ctx.get("ultrasonic_names", set())
            if owner.id in sensors:
                return "float"

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fname = node.func.id

        arg_types: List[str] = []
        for arg in node.args:
            arg_types.append(
                _infer_expr_type(
                    arg,
                    var_types,
                    functions,
                    function_param_types,
                    function_param_orders,
                    ctx,
                )
            )

        if fname in _BUILTIN_CALL_RETURN_TYPES:
            return _BUILTIN_CALL_RETURN_TYPES[fname]

        signature = tuple(arg_types)
        if ctx is not None:
            signature_map: Dict[str, List[Tuple[str, ...]]] = ctx.setdefault(
                "function_call_signatures", {}
            )
            recorded = signature_map.setdefault(fname, [])
            if signature not in recorded:
                recorded.append(signature)
            _ensure_function_variant(fname, signature, ctx)
        if functions and fname in functions:
            variants = functions[fname]
            if isinstance(variants, dict):
                canonical = _resolve_signature_alias(fname, signature, ctx or {})
                if canonical in variants:
                    return variants[canonical]
                if signature in variants:
                    return variants[signature]
                for candidate_sig, return_type in variants.items():
                    if len(candidate_sig) == len(signature):
                        return return_type
            else:
                return variants

    if isinstance(node, ast.BinOp):
        left = _infer_expr_type(
            node.left,
            var_types,
            functions,
            function_param_types,
            function_param_orders,
            ctx,
        )
        right = _infer_expr_type(
            node.right,
            var_types,
            functions,
            function_param_types,
            function_param_orders,
            ctx,
        )
        if "String" in (left, right):
            if isinstance(node.left, ast.Name) and left != "String":
                var_types[node.left.id] = "String"
                left = "String"
            if isinstance(node.right, ast.Name) and right != "String":
                var_types[node.right.id] = "String"
                right = "String"
            return "String"
        if "float" in (left, right):
            return "float"
        return "int"

    return "int"


def _cpp_type(py_type: str) -> str:
    """Translate a coarse Python type label into a C++ declaration type."""

    if _is_list_type(py_type):
        element_cpp = _cpp_type(_list_element_type(py_type))
        return f"__redu_list<{element_cpp}>"

    mapping = {
        "int": "int",
        "float": "float",
        "bool": "bool",
        "String": "String",
        "void": "void",
    }
    return mapping.get(py_type, "int")


def _default_value_for_type(c_type: str) -> str:
    """Return a sensible default initializer for the requested C++ type."""

    if c_type == "bool":
        return "false"
    if c_type == "float":
        return "0.0"
    if c_type == "String":
        return '""'
    if c_type.startswith("__redu_list<"):
        return f"{c_type}()"
    return "0"


def _expr_has_name(node: ast.AST) -> bool:
    """Return True if the expression tree references any identifiers."""

    if isinstance(node, ast.Name):
        return node.id not in _SAFE_NAME_REFERENCES
    return any(_expr_has_name(child) for child in ast.iter_child_nodes(node))


def _extract_call_argument(
    args_src: str,
    *,
    position: int = 0,
    keyword: Optional[str] = None,
) -> Optional[str]:
    """Return the source for a positional/keyword argument inside a call snippet.

    ``args_src`` should be the textual contents that appear between the
    parentheses of the original call expression. The helper uses ``ast`` to
    parse the snippet, falling back to the raw string for the primary positional
    argument if parsing fails. ``None`` is returned when no matching argument is
    present.
    """

    text = args_src.strip()
    if not text:
        return None

    try:
        call_expr = ast.parse(f"__redu_tmp({text})", mode="eval").body
    except SyntaxError:
        if keyword is None and position == 0:
            return text
        return None

    if not isinstance(call_expr, ast.Call):
        if keyword is None and position == 0:
            return text
        return None

    selected: Optional[ast.AST] = None
    if keyword is not None:
        for kw in call_expr.keywords:
            if kw.arg == keyword:
                selected = kw.value
                break

    if (
        selected is None
        and keyword is None
        and position is not None
        and len(call_expr.args) > position
    ):
        selected = call_expr.args[position]

    if selected is None:
        return None

    return ast.unparse(selected).strip()


def _strip_inline_comment(text: str) -> str:
    """Remove a trailing comment from ``text`` while respecting string literals."""

    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return text[:index].rstrip()
    return text


def _annotation_to_type_label(annotation: Optional[ast.AST]) -> str:
    """Translate a Python annotation node into an internal type label."""

    if annotation is None:
        return "int"

    if isinstance(annotation, ast.Constant):
        value = annotation.value
        if value in (None, "None"):
            return "void"
        if isinstance(value, str) and value.lower() == "string":
            return "String"

    if isinstance(annotation, ast.Name):
        name = annotation.id
    elif isinstance(annotation, ast.Attribute):
        parts: List[str] = []
        node: ast.AST = annotation
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            name = ".".join(reversed(parts))
        else:
            return "int"
    else:
        try:
            name = ast.unparse(annotation)
        except Exception:
            return "int"

    mapping = {
        "int": "int",
        "float": "float",
        "bool": "bool",
        "str": "String",
        "String": "String",
        "None": "void",
        "void": "void",
    }
    return mapping.get(name, "int")


def _merge_return_types(types: List[str], has_void: bool) -> str:
    """Combine multiple inferred return types into a single representative type."""

    unique = {t for t in types if t}
    if has_void:
        if unique:
            raise ValueError("cannot mix value and bare return statements")
        return "void"

    if not unique:
        return "void"

    if "String" in unique:
        if len(unique) > 1:
            raise ValueError("conflicting return types")
        return "String"

    if "float" in unique:
        return "float"

    if unique == {"bool"}:
        return "bool"

    if "int" in unique:
        return "int"

    if len(unique) == 1:
        return unique.pop()

    return "int"


# Imports to ignore
RE_IMPORT_LED     = re.compile(r"^\s*from\s+Reduino\.Actuators\s+import\s+Led\s*$")
RE_IMPORT_RGB_LED = re.compile(r"^\s*from\s+Reduino\.Actuators\s+import\s+RGBLed\s*$")
RE_IMPORT_SERVO   = re.compile(r"^\s*from\s+Reduino\.Actuators\s+import\s+Servo\s*$")
RE_IMPORT_BUZZER  = re.compile(r"^\s*from\s+Reduino\.Actuators\s+import\s+Buzzer\s*$")
RE_IMPORT_SLEEP   = re.compile(r"^\s*from\s+Reduino\.Utils\s+import\s+sleep\s*$")
RE_IMPORT_SERIAL  = re.compile(r"^\s*from\s+Reduino\.Communication\s+import\s+SerialMonitor\s*$")
RE_IMPORT_TARGET  = re.compile(r"^\s*from\s+Reduino\s+import\s+target\s*$")
RE_IMPORT_ULTRASONIC = re.compile(r"^\s*from\s+Reduino\.Sensors\s+import\s+Ultrasonic\s*$")
RE_IMPORT_BUTTON  = re.compile(r"^\s*from\s+Reduino\.Sensors\s+import\s+Button\s*$")
RE_IMPORT_LCD     = re.compile(r"^\s*from\s+Reduino\.Displays\s+import\s+LCD\s*$")
RE_IMPORT_POTENTIOMETER = re.compile(
    r"^\s*from\s+Reduino\.Sensors\s+import\s+Potentiometer\s*$"
)

# Led Primitives
RE_ASSIGN     = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+)$")
RE_LED_DECL   = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*Led\s*\(\s*(.*?)\s*\)\s*$")
RE_BUZZER_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*Buzzer\s*\(\s*(.*?)\s*\)\s*$")
RE_RGB_LED_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*RGBLed\s*\(\s*(.*?)\s*\)\s*$")
RE_SERVO_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*Servo\s*\(\s*(.*?)\s*\)\s*$")
RE_ULTRASONIC_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*Ultrasonic\s*\(\s*(.*?)\s*\)\s*$")
RE_BUTTON_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*Button\s*\(\s*(.*?)\s*\)\s*$")
RE_POTENTIOMETER_DECL = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*=\s*Potentiometer\s*\(\s*(.*?)\s*\)\s*$"
)
RE_LED_ON         = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.on\(\s*\)\s*$")
RE_LED_OFF        = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.off\(\s*\)\s*$")
RE_LED_TOGGLE     = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.toggle\(\s*\)\s*$")
RE_LED_SET_BRIGHTNESS = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.set_brightness\(\s*(.*)\s*\)\s*$")
RE_LED_BLINK      = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.blink\(\s*(.*)\s*\)\s*$")
RE_LED_FADE_IN    = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.fade_in\(\s*(.*)\s*\)\s*$")
RE_LED_FADE_OUT   = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.fade_out\(\s*(.*)\s*\)\s*$")
RE_LED_FLASH_PATTERN = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.flash_pattern\(\s*(.*)\s*\)\s*$")
RE_BUZZER_PLAY_TONE  = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.play_tone\(\s*(.*)\s*\)\s*$")
RE_BUZZER_STOP       = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.stop\(\s*\)\s*$")
RE_BUZZER_BEEP       = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.beep\(\s*(.*)\s*\)\s*$")
RE_BUZZER_SWEEP      = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.sweep\(\s*(.*)\s*\)\s*$")
RE_BUZZER_MELODY     = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.melody\(\s*(.*)\s*\)\s*$")
RE_RGB_LED_ON        = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.on\(\s*(.*)\s*\)\s*$")
RE_RGB_LED_OFF       = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.off\(\s*\)\s*$")
RE_RGB_LED_SET_COLOR = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.set_color\(\s*(.*)\s*\)\s*$")
RE_RGB_LED_FADE      = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.fade\(\s*(.*)\s*\)\s*$")
RE_RGB_LED_BLINK     = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.blink\(\s*(.*)\s*\)\s*$")
RE_SERVO_WRITE       = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.write\(\s*(.*)\s*\)\s*$")
RE_SERVO_WRITE_US    = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.write_us\(\s*(.*)\s*\)\s*$")

_BUZZER_MELODIES = {
    "success",
    "error",
    "startup",
    "notify",
    "alarm",
    "scale_c",
    "siren",
}

# Serial primitives
RE_SERIAL_DECL    = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*SerialMonitor\s*\(\s*(.*?)\s*\)\s*$")
RE_SERIAL_WRITE   = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.write\(\s*(.*?)\s*\)\s*$")

#Time Primitives
RE_SLEEP_EXPR = re.compile(r"^\s*sleep\s*\(\s*(.+?)\s*\)\s*$")

# Build directive: regex for target device
RE_TARGET_CALL = re.compile(r"""^\s*target\s*\(\s*(?:['"])?\s*([A-Za-z0-9:_\-./\\~]+)\s*(?:['"])?\s*\)\s*$""")
RE_TARGET_INLINE = re.compile(
    r"""(?<!\.)\btarget\s*\(\s*(?:['"])?\s*([A-Za-z0-9:_\-./\\~]+)\s*(?:['"])?\s*\)"""
)

# Top-level control
RE_WHILE_TRUE     = re.compile(r"^\s*while\s+True\s*:\s*$")
RE_WHILE          = re.compile(r"^\s*while\s+(.+?)\s*:\s*$")
RE_FOR_RANGE      = re.compile(
    r"^\s*for\s+([A-Za-z_]\w*)\s+in\s+range\((.*)\)\s*:\s*$"
)
RE_IF             = re.compile(r"^\s*if\s+(.+?)\s*:\s*$")
RE_ELIF           = re.compile(r"^\s*elif\s+(.+?)\s*:\s*$")
RE_ELSE           = re.compile(r"^\s*else\s*:\s*$")
RE_TRY            = re.compile(r"^\s*try\s*:\s*$")
RE_EXCEPT         = re.compile(
    r"^\s*except(?:\s+([A-Za-z_][\w.]*))?(?:\s+as\s+([A-Za-z_]\w*))?\s*:\s*$"
)
RE_DEF            = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*:\s*$")

def _indent_of(line: str) -> int:
    i = 0
    for ch in line:
        if ch == ' ':
            i += 1
        elif ch == '\t':
            i += 4
        else:
            break
    return i

def _collect_block(lines: List[str], start: int) -> Tuple[List[str], int]:
    base = _indent_of(lines[start])
    i = start + 1
    block: List[str] = []
    while i < len(lines):
        if not lines[i].strip():
            block.append(lines[i]); i += 1; continue
        if _indent_of(lines[i]) <= base:
            break
        block.append(lines[i]); i += 1
    return block, i


def _collect_while_structure(lines: List[str], start: int) -> Tuple[List[str], int]:
    snippet: List[str] = [lines[start]]
    block, i = _collect_block(lines, start)
    snippet.extend(block)
    return snippet, i


def _collect_for_structure(lines: List[str], start: int) -> Tuple[List[str], int]:
    snippet: List[str] = [lines[start]]
    block, i = _collect_block(lines, start)
    snippet.extend(block)
    return snippet, i


def _collect_if_structure(lines: List[str], start: int) -> Tuple[List[str], int]:
    base = _indent_of(lines[start])
    snippet: List[str] = [lines[start]]
    block, i = _collect_block(lines, start)
    snippet.extend(block)
    while i < len(lines):
        raw = lines[i]
        text = raw.strip()
        if not text:
            snippet.append(raw)
            i += 1
            continue
        if _indent_of(raw) != base:
            break
        if RE_ELIF.match(text) or RE_ELSE.match(text):
            snippet.append(raw)
            branch_block, i = _collect_block(lines, i)
            snippet.extend(branch_block)
            continue
        break
    return snippet, i


def _collect_try_structure(lines: List[str], start: int) -> Tuple[List[str], int]:
    base = _indent_of(lines[start])
    snippet: List[str] = [lines[start]]
    block, i = _collect_block(lines, start)
    snippet.extend(block)
    while i < len(lines):
        raw = lines[i]
        text = raw.strip()
        if not text:
            snippet.append(raw)
            i += 1
            continue
        if _indent_of(raw) != base:
            break
        if RE_EXCEPT.match(text):
            snippet.append(raw)
            branch_block, i = _collect_block(lines, i)
            snippet.extend(branch_block)
            continue
        break
    return snippet, i


def _parse_function(
    name: str,
    params_src: str,
    block: List[str],
    ctx: Dict[str, object],
    *,
    forced_signature: Optional[Tuple[str, ...]] = None,
) -> FunctionDef:
    """Parse a ``def`` block into a :class:`FunctionDef` node."""

    header_src = f"def {name}({params_src}):\n    0\n"
    try:
        header_ast = ast.parse(header_src, mode="exec")
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise ValueError("invalid function definition") from exc
    if not header_ast.body or not isinstance(header_ast.body[0], ast.FunctionDef):
        raise ValueError("invalid function definition")

    fn_ast: ast.FunctionDef = header_ast.body[0]
    if fn_ast.args.vararg or fn_ast.args.kwarg:
        raise ValueError("*args/**kwargs are not supported in Reduino functions")
    if fn_ast.args.kwonlyargs or fn_ast.args.kw_defaults:
        raise ValueError("keyword-only arguments are not supported")
    if fn_ast.args.defaults:
        raise ValueError("default argument values are not supported")

    all_args = list(fn_ast.args.posonlyargs) + list(fn_ast.args.args)

    annotated_return = (
        _annotation_to_type_label(fn_ast.returns)
        if fn_ast.returns is not None
        else None
    )

    ctx.setdefault("function_sources", {})[name] = (params_src, list(block))

    helpers_set = ctx.setdefault("helpers", set())
    functions_map: Dict[str, Dict[Tuple[str, ...], str]] = ctx.setdefault(
        "functions", {}
    )
    param_orders: Dict[str, List[str]] = ctx.setdefault("function_param_orders", {})
    param_types: Dict[str, Dict[int, str]] = ctx.setdefault("function_param_types", {})
    signature_aliases: Dict[str, Dict[Tuple[str, ...], Tuple[str, ...]]] = ctx.setdefault(
        "function_signature_aliases", {}
    )
    defs: Dict[str, Dict[Tuple[str, ...], FunctionDef]] = ctx.setdefault(
        "function_defs", {}
    )

    functions_map.setdefault(name, {})
    signature_aliases.setdefault(name, {})
    defs.setdefault(name, {})

    child_ctx: Dict[str, object] = dict(ctx)
    child_ctx["vars"] = dict(ctx.get("vars", {}))
    child_ctx["var_types"] = dict(ctx.get("var_types", {}))
    child_ctx["var_declared"] = set(ctx.get("var_declared", set()))
    child_ctx["_base_declared"] = set(child_ctx["var_declared"])
    child_ctx["globals"] = ctx.setdefault("globals", [])
    child_ctx["helpers"] = helpers_set
    child_ctx["vars"].setdefault("_helpers", helpers_set)
    child_ctx["functions"] = functions_map
    if "tmp_counter" in ctx:
        child_ctx["tmp_counter"] = ctx["tmp_counter"]

    fn_meta: Dict[str, object] = {"return_types": [], "has_void": False}
    child_ctx["current_function"] = fn_meta

    params_order: List[Tuple[str, int]] = []
    param_names: List[str] = []
    orders_entry = param_orders.setdefault(name, [])
    orders_entry[:] = []
    type_entry = param_types.setdefault(name, {})

    if forced_signature is not None and len(forced_signature) != len(all_args):
        raise ValueError("call signature arity does not match function definition")

    for idx, arg in enumerate(all_args):
        if forced_signature is not None:
            param_type_label = forced_signature[idx]
        else:
            param_type_label = _annotation_to_type_label(arg.annotation)
            if arg.annotation is None and idx in type_entry:
                param_type_label = type_entry[idx]
        child_ctx["var_types"][arg.arg] = param_type_label
        child_ctx["var_declared"].add(arg.arg)
        child_ctx["vars"][arg.arg] = _ExprStr(arg.arg)
        params_order.append((arg.arg, idx))
        param_names.append(arg.arg)

    body_nodes = _parse_simple_lines(
        block,
        child_ctx,
        scope="function",
        depth=1,
        loop_depth=0,
        main_loop=False,
    )

    if "tmp_counter" in child_ctx:
        ctx["tmp_counter"] = child_ctx["tmp_counter"]

    return_types: List[str] = fn_meta.get("return_types", [])
    has_void = bool(fn_meta.get("has_void"))
    merged_return = _merge_return_types(return_types, has_void)
    if merged_return == "void" and annotated_return and annotated_return != "void":
        merged_return = annotated_return
    elif annotated_return and annotated_return != merged_return and return_types:
        merged_return = annotated_return

    resolved_param_types: List[str] = []
    params: List[Tuple[str, str]] = []
    for param_name, idx in params_order:
        resolved_label = child_ctx["var_types"].get(param_name, type_entry.get(idx, "int"))
        type_entry[idx] = resolved_label
        resolved_param_types.append(resolved_label)
        params.append((param_name, _cpp_type(resolved_label)))

    final_signature = tuple(resolved_param_types)
    requested_signature = tuple(forced_signature) if forced_signature is not None else final_signature

    functions_map[name][final_signature] = merged_return
    if requested_signature != final_signature:
        signature_aliases[name][requested_signature] = final_signature
        functions_map[name][requested_signature] = merged_return

    orders_entry.extend(param_names)

    existing = defs[name].get(final_signature)
    if existing is None:
        func_node = FunctionDef(
            name=name,
            params=params,
            body=body_nodes,
            return_type=_cpp_type(merged_return),
        )
        defs[name][final_signature] = func_node
    else:
        existing.params = params
        existing.body = body_nodes
        existing.return_type = _cpp_type(merged_return)
        func_node = existing

    if forced_signature is None:
        ctx.setdefault("function_primary_signature", {})[name] = final_signature
        pending = ctx.get("function_call_signatures", {}).get(name, [])
        for requested in pending:
            if requested != final_signature:
                _ensure_function_variant(name, requested, ctx)

    return func_node


def _handle_assignment_ast(
    line: str,
    ctx: Dict[str, object],
    scope: str,
    depth: int,
) -> Optional[List[object]]:
    """Handle Python-style assignment statements and return emitted nodes."""

    try:
        node = ast.parse(line, mode="exec")
    except SyntaxError:
        return None
    if not node.body:
        return None

    stmt = node.body[0]

    if isinstance(stmt, ast.Assign):
        assign: ast.Assign = stmt

        if len(assign.targets) != 1:
            return None

        target = assign.targets[0]
        value = assign.value

    elif isinstance(stmt, ast.AugAssign):
        target = stmt.target
        value = stmt.value
    else:
        return None

    def is_led_call(n: ast.AST) -> bool:
        return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Led"

    def is_rgb_led_call(n: ast.AST) -> bool:
        return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "RGBLed"

    def is_servo_call(n: ast.AST) -> bool:
        return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Servo"

    def is_buzzer_call(n: ast.AST) -> bool:
        return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Buzzer"

    def is_serial_monitor_call(n: ast.AST) -> bool:
        return (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "SerialMonitor"
        )

    def is_ultrasonic_call(n: ast.AST) -> bool:
        return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Ultrasonic"

    def is_lcd_call(n: ast.AST) -> bool:
        return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "LCD"

    if isinstance(target, ast.Name) and (
        is_led_call(value)
        or is_rgb_led_call(value)
        or is_servo_call(value)
        or is_buzzer_call(value)
        or is_serial_monitor_call(value)
        or is_ultrasonic_call(value)
        or is_lcd_call(value)
    ):
        return None
    if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
        if any(
            is_led_call(elt)
            or is_rgb_led_call(elt)
            or is_servo_call(elt)
            or is_buzzer_call(elt)
            or is_serial_monitor_call(elt)
            or is_ultrasonic_call(elt)
            or is_lcd_call(elt)
            for elt in value.elts
        ):
            return None

    vars_env = ctx.setdefault("vars", {})
    vars_env["_ctx"] = ctx
    helpers = ctx.setdefault("helpers", set())
    vars_env.setdefault("_helpers", helpers)
    var_types = ctx.setdefault("var_types", {})
    declared: set = ctx.setdefault("var_declared", set())
    globals_list: List[VarDecl] = ctx.setdefault("globals", [])
    functions_map: Dict[str, str] = ctx.setdefault("functions", {})
    function_param_types = ctx.setdefault("function_param_types", {})
    function_param_orders = ctx.setdefault("function_param_orders", {})
    list_info: Dict[str, Dict[str, Optional[int]]] = ctx.setdefault("list_info", {})

    def eval_or_expr(expr_node: ast.AST) -> Tuple[str, str, object, bool]:
        src = line[expr_node.col_offset : expr_node.end_col_offset]
        try:
            value_obj = _eval_const(src, vars_env)
            return src, _to_c_expr(src, vars_env, ctx), value_obj, True
        except Exception:
            c_expr = _to_c_expr(src, vars_env, ctx)
            return src, c_expr, _ExprStr(c_expr), False

    def list_length_from_ast(expr_node: ast.AST) -> Optional[int]:
        if isinstance(expr_node, ast.List):
            return len(expr_node.elts)
        if isinstance(expr_node, ast.Name):
            info = list_info.get(expr_node.id)
            if info is not None:
                return info.get("length")
        return None

    def record_list_state(
        name: str,
        type_label: str,
        expr_node: ast.AST,
        value_obj: object,
    ) -> None:
        if not _is_list_type(type_label):
            list_info.pop(name, None)
            return
        helpers.add("list")
        length: Optional[int] = None
        if isinstance(value_obj, list):
            length = len(value_obj)
        else:
            length = list_length_from_ast(expr_node)
        entry = list_info.setdefault(name, {})
        entry["elem"] = _list_element_type(type_label)
        entry["length"] = length

    nodes: List[object] = []
    is_global_scope = scope == "setup" and depth == 0

    if isinstance(stmt, ast.AugAssign):
        if not isinstance(target, ast.Name):
            return None
        op_symbol = _BIN.get(type(stmt.op))
        if op_symbol is None:
            return None
        rhs_src = line[value.col_offset : value.end_col_offset]
        rhs_c = _to_c_expr(rhs_src, vars_env, ctx)
        bin_node = ast.BinOp(
            left=ast.Name(id=target.id, ctx=ast.Load()),
            op=stmt.op,
            right=value,
        )
        inferred_type = _infer_expr_type(
            bin_node,
            var_types,
            functions_map,
            function_param_types,
            function_param_orders,
            ctx,
        )
        var_types[target.id] = inferred_type
        vars_env[target.id] = _ExprStr(target.id)
        nodes.append(VarAssign(name=target.id, expr=f"({target.id} {op_symbol} {rhs_c})"))
        return nodes

    if isinstance(target, ast.Name):
        _, expr_c, value_obj, is_const = eval_or_expr(value)
        expr_uses_names = _expr_has_name(value)
        inferred_type = _infer_expr_type(
            value,
            var_types,
            functions_map,
            function_param_types,
            function_param_orders,
            ctx,
        )
        existing_type = var_types.get(target.id)
        is_declared = target.id in declared
        if is_declared and _is_list_type(existing_type or ""):
            if not _is_list_type(inferred_type):
                raise ValueError("cannot assign non-list to list variable")
            new_length = None
            if isinstance(value_obj, list):
                new_length = len(value_obj)
            else:
                new_length = list_length_from_ast(value)
            expected = list_info.get(target.id, {}).get("length")
            if expected is not None and new_length is not None and expected != new_length:
                raise ValueError("list assignment size mismatch")
            old_elem = _list_element_type(existing_type) if existing_type else None
            new_elem = _list_element_type(inferred_type)
            if old_elem is not None and old_elem != new_elem:
                raise ValueError("conflicting list element types")
        if _is_list_type(inferred_type):
            helpers.add("list")
        var_types[target.id] = inferred_type
        vars_env[target.id] = value_obj
        record_list_state(target.id, inferred_type, value, value_obj)
        needs_clone = is_declared and _is_list_type(inferred_type)
        assign_expr = expr_c
        assign_as_expr_stmt = False
        if needs_clone:
            assign_expr = f"__redu_list_assign({target.id}, {expr_c})"
            assign_as_expr_stmt = True
            helpers.add("list")
        if target.id not in declared:
            declared.add(target.id)
            cpp_type = _cpp_type(inferred_type)
            needs_runtime_assign = False
            init_expr = expr_c
            if is_global_scope:
                if not is_const or expr_uses_names:
                    init_expr = _default_value_for_type(cpp_type)
                    needs_runtime_assign = True
            decl = VarDecl(
                name=target.id,
                c_type=cpp_type,
                expr=init_expr,
                global_scope=is_global_scope,
            )
            if is_global_scope:
                globals_list.append(decl)
                if needs_runtime_assign:
                    if assign_as_expr_stmt:
                        nodes.append(ExprStmt(expr=assign_expr))
                    else:
                        nodes.append(VarAssign(name=target.id, expr=assign_expr))
            else:
                nodes.append(decl)
                if needs_runtime_assign:
                    if assign_as_expr_stmt:
                        nodes.append(ExprStmt(expr=assign_expr))
                    else:
                        nodes.append(VarAssign(name=target.id, expr=assign_expr))
        else:
            if assign_as_expr_stmt:
                nodes.append(ExprStmt(expr=assign_expr))
            else:
                nodes.append(VarAssign(name=target.id, expr=assign_expr))
        return nodes

    if isinstance(target, (ast.Tuple, ast.List)):
        left_names: List[str] = []
        for elt in target.elts:
            if isinstance(elt, ast.Name):
                left_names.append(elt.id)
            else:
                return None

        if not isinstance(value, (ast.Tuple, ast.List)):
            return None

        right_data = [eval_or_expr(elt) for elt in value.elts[: len(left_names)]]
        evaluated_values = [data[2] for data in right_data]
        inferred_types = [
            _infer_expr_type(
                elt,
                var_types,
                functions_map,
                function_param_types,
                function_param_orders,
                ctx,
            )
            for elt in value.elts[: len(left_names)]
        ]

        for idx, name in enumerate(left_names):
            var_types[name] = inferred_types[idx]

        # Decide if we can emit simple declarations (all new + global scope)
        all_new = all(name not in declared for name in left_names)
        if all_new and is_global_scope:
            for idx, name in enumerate(left_names):
                declared.add(name)
                vars_env[name] = evaluated_values[idx]
                cpp_type = _cpp_type(inferred_types[idx])
                expr_c = right_data[idx][1]
                is_const = right_data[idx][3]
                uses_names = _expr_has_name(value.elts[idx])
                needs_runtime_assign = not is_const or uses_names
                init_expr = (
                    expr_c if not needs_runtime_assign else _default_value_for_type(cpp_type)
                )
                globals_list.append(
                    VarDecl(
                        name=name,
                        c_type=cpp_type,
                        expr=init_expr,
                        global_scope=True,
                    )
                )
                if needs_runtime_assign:
                    nodes.append(VarAssign(name=name, expr=expr_c))
            return nodes

        tmp_nodes: List[object] = []
        tmp_names: List[str] = []
        for idx, data in enumerate(right_data):
            expr_c = data[1]
            inferred = inferred_types[idx]
            tmp_name = f"__tmp_assign_{ctx.setdefault('tmp_counter', 0)}"
            ctx["tmp_counter"] = ctx.get("tmp_counter", 0) + 1
            tmp_names.append(tmp_name)
            tmp_nodes.append(
                VarDecl(
                    name=tmp_name,
                    c_type=_cpp_type(inferred),
                    expr=expr_c,
                    global_scope=False,
                )
            )

        nodes.extend(tmp_nodes)

        for idx, name in enumerate(left_names):
            vars_env[name] = evaluated_values[idx]
            if name not in declared:
                declared.add(name)
                nodes.append(
                    VarDecl(
                        name=name,
                        c_type=_cpp_type(inferred_types[idx]),
                        expr=tmp_names[idx],
                        global_scope=False,
                    )
                )
            else:
                nodes.append(VarAssign(name=name, expr=tmp_names[idx]))

        return nodes

    return None


def _promote_branch_decls(
    branch_entries: List[Tuple[Dict[str, object], List[object]]],
    else_entry: Optional[Tuple[Dict[str, object], List[object]]],
    parent_ctx: Dict[str, object],
    scope: str,
    depth: int,
) -> List[str]:
    """Determine which variables declared in branches should be lifted outward."""

    if not branch_entries:
        return []

    parent_declared: set = parent_ctx.setdefault("var_declared", set())
    parent_types: Dict[str, str] = parent_ctx.setdefault("var_types", {})

    coverage: Dict[str, int] = {}
    inferred: Dict[str, str] = {}
    order: List[str] = []

    def record(name: str, child_ctx: Dict[str, object]) -> None:
        if name in parent_declared:
            return
        if name not in coverage:
            coverage[name] = 0
            order.append(name)
            inferred[name] = child_ctx.get("var_types", {}).get(name, "int")
        coverage[name] += 1

    for child_ctx, _ in branch_entries:
        base = child_ctx.get("_base_declared", set())
        new_names = child_ctx.get("var_declared", set()) - base
        for name in new_names:
            record(name, child_ctx)

    if else_entry is not None:
        else_ctx, _ = else_entry
        base = else_ctx.get("_base_declared", set())
        new_names = else_ctx.get("var_declared", set()) - base
        for name in new_names:
            record(name, else_ctx)

    if not order:
        return []

    promotion_info = parent_ctx.setdefault("_promotion_cpp_types", {})
    for name in order:
        py_type = inferred.get(name, "int")
        parent_types[name] = py_type
        promotion_info[name] = _cpp_type(py_type)

    return order


def _make_promotion_decls(
    promoted_names: List[str],
    ctx: Dict[str, object],
    scope: str,
    depth: int,
) -> List[VarDecl]:
    """Emit declarations for variables promoted out of conditional branches."""

    if not promoted_names:
        return []

    globals_list: List[VarDecl] = ctx.setdefault("globals", [])
    declared: set = ctx.setdefault("var_declared", set())
    vars_env: Dict[str, object] = ctx.setdefault("vars", {})
    var_types: Dict[str, str] = ctx.setdefault("var_types", {})
    promotion_info: Dict[str, str] = ctx.setdefault("_promotion_cpp_types", {})

    declarations: List[VarDecl] = []
    for name in promoted_names:
        cpp_type = promotion_info.get(name, _cpp_type(var_types.get(name, "int")))
        decl = VarDecl(
            name=name,
            c_type=cpp_type,
            expr=_default_value_for_type(cpp_type),
            global_scope=scope == "setup" and depth == 0,
        )
        if decl.global_scope:
            if all(existing.name != name for existing in globals_list):
                globals_list.append(decl)
        else:
            declarations.append(decl)
        declared.add(name)
        vars_env[name] = _ExprStr(name)
        if name not in var_types:
            var_types[name] = "int"

    return declarations


def _rewrite_nodes(nodes: List[object], promoted: Set[str]) -> List[object]:
    """Rewrite nodes, replacing declarations of promoted names with assignments."""

    rewritten: List[object] = []
    for node in nodes:
        if isinstance(node, VarDecl) and node.name in promoted:
            rewritten.append(VarAssign(name=node.name, expr=node.expr))
            continue
        if isinstance(node, IfStatement):
            new_branches = [
                ConditionalBranch(
                    condition=branch.condition,
                    body=_rewrite_nodes(branch.body, promoted),
                )
                for branch in node.branches
            ]
            new_else = _rewrite_nodes(node.else_body, promoted)
            rewritten.append(IfStatement(branches=new_branches, else_body=new_else))
            continue
        if isinstance(node, WhileLoop):
            rewritten.append(
                WhileLoop(
                    condition=node.condition,
                    body=_rewrite_nodes(node.body, promoted),
                )
            )
            continue
        if isinstance(node, ForRangeLoop):
            rewritten.append(
                ForRangeLoop(
                    var_name=node.var_name,
                    count=node.count,
                    body=_rewrite_nodes(node.body, promoted),
                )
            )
            continue
        if isinstance(node, TryStatement):
            rewritten.append(
                TryStatement(
                    try_body=_rewrite_nodes(node.try_body, promoted),
                    handlers=[
                        CatchClause(
                            exception=handler.exception,
                            target=handler.target,
                            body=_rewrite_nodes(handler.body, promoted),
                        )
                        for handler in node.handlers
                    ],
                )
            )
            continue
        rewritten.append(node)
    return rewritten


def _parse_simple_lines(
    snippet: List[str],
    ctx: Dict[str, object],
    scope: str,
    depth: int = 0,
    *,
    loop_depth: int = 0,
    main_loop: bool = False,
) -> List[object]:
    """Parse a flat sequence of statements into AST nodes."""

    body: List[object] = []
    vars = ctx.setdefault("vars", {})
    vars["_ctx"] = ctx
    helpers = ctx.setdefault("helpers", set())
    vars.setdefault("_helpers", helpers)
    ctx.setdefault("globals", [])
    var_types = ctx.setdefault("var_types", {})
    ctx.setdefault("var_declared", set())
    ctx.setdefault("functions", {})
    list_info = ctx.setdefault("list_info", {})
    rgb_led_names = ctx.setdefault("rgb_led_names", set())
    lcd_names = ctx.setdefault("lcd_names", set())
    lcd_tick_names = ctx.setdefault("lcd_tick_names", set())
    servo_names = ctx.setdefault("servo_names", set())
    buzzer_names = ctx.setdefault("buzzer_names", set())
    button_names = ctx.setdefault("button_names", set())
    button_pins = ctx.setdefault("button_pins", {})
    button_callbacks = ctx.setdefault("button_callbacks", {})
    button_poll_names = ctx.setdefault("button_poll_names", set())

    def _resolve_numeric_arg(arg_src: Optional[str], default: Union[int, str]) -> Union[int, str]:
        if arg_src is None or not arg_src.strip():
            return default
        try:
            expr_ast = ast.parse(arg_src, mode="eval").body
        except Exception:
            expr_ast = None
        if expr_ast is not None and not _expr_has_name(expr_ast):
            try:
                value = _eval_const(arg_src, vars)
            except Exception:
                pass
            else:
                if isinstance(value, bool):
                    return 1 if value else 0
                if isinstance(value, (int, float)):
                    return int(value)
        return _to_c_expr(arg_src, vars, ctx)

    def _resolve_float_arg(
        arg_src: Optional[str], default: Union[float, int, str]
    ) -> Union[float, int, str]:
        if arg_src is None or not arg_src.strip():
            return default
        try:
            expr_ast = ast.parse(arg_src, mode="eval").body
        except Exception:
            expr_ast = None
        if expr_ast is not None and not _expr_has_name(expr_ast):
            try:
                value = _eval_const(arg_src, vars)
            except Exception:
                pass
            else:
                if isinstance(value, bool):
                    return 1.0 if value else 0.0
                if isinstance(value, (int, float)):
                    return float(value)
        return _to_c_expr(arg_src, vars, ctx)

    def _resolve_optional_numeric_arg(
        arg_src: Optional[str],
    ) -> Optional[Union[int, str]]:
        if arg_src is None:
            return None
        text = arg_src.strip()
        if not text or text == "None":
            return None
        try:
            expr_ast = ast.parse(text, mode="eval").body
        except Exception:
            expr_ast = None
        if expr_ast is not None and not _expr_has_name(expr_ast):
            try:
                value = _eval_const(text, vars)
            except Exception:
                pass
            else:
                if isinstance(value, bool):
                    return 1 if value else 0
                if isinstance(value, (int, float)):
                    return int(value)
        return _to_c_expr(text, vars, ctx)

    def _resolve_bool_arg(arg_src: Optional[str], default: bool) -> Union[bool, str]:
        if arg_src is None or not arg_src.strip():
            return default
        text = arg_src.strip()
        try:
            expr_ast = ast.parse(text, mode="eval").body
        except Exception:
            expr_ast = None
        if expr_ast is not None and not _expr_has_name(expr_ast):
            try:
                value = _eval_const(text, vars)
            except Exception:
                pass
            else:
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return bool(value)
        return _to_c_expr(text, vars, ctx)

    def _require_string_literal(arg_src: Optional[str], label: str) -> str:
        if arg_src is None:
            raise ValueError(f"{label} must be provided")
        text = arg_src.strip()
        try:
            expr_ast = ast.parse(text, mode="eval").body
        except Exception as exc:
            raise ValueError(f"{label} must be a string literal") from exc
        if not (isinstance(expr_ast, ast.Constant) and isinstance(expr_ast.value, str)):
            raise ValueError(f"{label} must be a string literal")
        return expr_ast.value

    def _resolve_align_arg(arg_src: Optional[str], default: str = "left") -> str:
        if arg_src is None or not arg_src.strip():
            return default
        value = _require_string_literal(arg_src, "align").lower()
        if value not in {"left", "center", "right"}:
            raise ValueError("align must be 'left', 'center' or 'right'")
        return value

    def _resolve_style_arg(arg_src: Optional[str], default: str = "block") -> str:
        allowed = {"block", "hash", "pipe", "dot"}
        if arg_src is None or not arg_src.strip():
            return default
        value = _require_string_literal(arg_src, "style").lower()
        if value not in allowed:
            options = ", ".join(sorted(allowed))
            raise ValueError(f"unknown progress style: {value!r} (choose from {options})")
        return value

    def _resolve_animation_arg(arg_src: Optional[str]) -> str:
        allowed = {"scroll", "blink", "typewriter", "bounce"}
        value = _require_string_literal(arg_src, "animation").lower()
        if value not in allowed:
            options = ", ".join(sorted(allowed))
            raise ValueError(
                f"unknown animation: {value!r} (choose from {options})"
            )
        return value

    i = 0
    while i < len(snippet):
        raw = snippet[i]
        stripped = _strip_inline_comment(raw)
        line = stripped.strip()
        if not line:
            i += 1
            continue
        if not line or line.startswith('#'):
            i += 1
            continue

        # ignore imports
        if (
            RE_IMPORT_LED.match(line)
            or RE_IMPORT_RGB_LED.match(line)
            or RE_IMPORT_SERVO.match(line)
            or RE_IMPORT_BUZZER.match(line)
            or RE_IMPORT_SLEEP.match(line)
            or RE_IMPORT_SERIAL.match(line)
            or RE_IMPORT_TARGET.match(line)
            or RE_IMPORT_ULTRASONIC.match(line)
            or RE_IMPORT_BUTTON.match(line)
            or RE_IMPORT_LCD.match(line)
        ):
            i += 1
            continue

        if line == "break":
            if loop_depth <= 0:
                raise ValueError("'break' outside loop is not supported")
            if main_loop and loop_depth == 1:
                raise ValueError("cannot break out of the main loop()")
            body.append(BreakStmt())
            i += 1
            continue

        if line.startswith("return"):
            func_meta = ctx.get("current_function")
            if func_meta is None:
                raise ValueError("'return' outside of a function is not supported")
            try:
                ret_module = ast.parse(line, mode="exec")
            except SyntaxError as exc:  # pragma: no cover - defensive
                raise ValueError("invalid return statement") from exc
            if not ret_module.body or not isinstance(ret_module.body[0], ast.Return):
                raise ValueError("invalid return statement")
            ret_stmt: ast.Return = ret_module.body[0]
            if ret_stmt.value is None:
                func_meta.setdefault("has_void", True)
                body.append(ReturnStmt(expr=None))
            else:
                expr_node = ret_stmt.value
                expr_src = line[expr_node.col_offset : expr_node.end_col_offset]
                expr_c = _to_c_expr(expr_src, vars, ctx)
                return_type = _infer_expr_type(
                    expr_node,
                    ctx.get("var_types", {}),
                    ctx.get("functions", {}),
                    ctx.get("function_param_types", {}),
                    ctx.get("function_param_orders", {}),
                    ctx,
                )
                func_meta.setdefault("return_types", []).append(return_type)
                func_meta.setdefault("return_nodes", []).append(expr_node)
                body.append(ReturnStmt(expr=expr_c))
            i += 1
            continue

        # capture target() directive
        m = RE_TARGET_CALL.match(line)
        if m:
            ctx["target_port"] = m.group(1)
            i += 1
            continue

        inline_matches = list(RE_TARGET_INLINE.finditer(line))
        if inline_matches:
            ctx["target_port"] = inline_matches[-1].group(1)
            i += 1
            continue

        m = RE_POTENTIOMETER_DECL.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            pin_arg = _extract_call_argument(args_src, keyword="pin")
            if pin_arg is None:
                pin_arg = _extract_call_argument(args_src)
            if pin_arg is None or not pin_arg.strip():
                raise ValueError("Potentiometer requires a pin argument")

            def _resolve_pot_pin(src_text: str) -> str:
                text = src_text.strip()
                try:
                    expr_ast = ast.parse(text, mode="eval").body
                except Exception as exc:  # pragma: no cover - defensive
                    raise ValueError(
                        "Potentiometer pin must be an analogue pin literal like A0"
                    ) from exc

                candidate: Optional[str]
                if isinstance(expr_ast, ast.Constant) and isinstance(expr_ast.value, str):
                    candidate = expr_ast.value
                elif isinstance(expr_ast, ast.Name):
                    candidate = expr_ast.id
                else:
                    raise ValueError(
                        "Potentiometer pin must be an analogue pin literal like A0"
                    )

                if not ANALOG_PIN_RE.fullmatch(candidate.strip()):
                    raise ValueError(
                        "Potentiometer pin must be an analogue pin literal like A0"
                    )
                return candidate.strip()

            pin_value = _resolve_pot_pin(pin_arg)

            ctx.setdefault("potentiometer_names", set()).add(name)
            ctx.setdefault("potentiometer_pins", {})[name] = pin_value
            vars[name] = _ExprStr(name)
            body.append(PotentiometerDecl(name=name, pin=pin_value))
            i += 1
            continue

        m = RE_BUTTON_DECL.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            pin_arg = _extract_call_argument(args_src, keyword="pin")
            if pin_arg is None:
                pin_arg = _extract_call_argument(args_src)
            if pin_arg is None or not pin_arg.strip():
                raise ValueError("Button requires a pin argument")

            def _resolve_button_pin(src_text: str) -> Union[int, str]:
                text = src_text.strip()
                try:
                    expr_ast = ast.parse(text, mode="eval").body
                except Exception:
                    expr_ast = None
                if expr_ast is not None and not _expr_has_name(expr_ast):
                    try:
                        value = _eval_const(text, vars)
                    except Exception:
                        pass
                    else:
                        if isinstance(value, bool):
                            return 1 if value else 0
                        if isinstance(value, (int, float)):
                            return int(value)
                return _to_c_expr(text, vars, ctx)

            pin_value = _resolve_button_pin(pin_arg)

            on_click_arg = _extract_call_argument(args_src, keyword="on_click")
            if on_click_arg is None:
                on_click_arg = _extract_call_argument(args_src, position=1)

            callback_name: Optional[str] = None
            if on_click_arg is not None and on_click_arg.strip():
                candidate = on_click_arg.strip()
                try:
                    expr_ast = ast.parse(candidate, mode="eval").body
                except Exception as exc:
                    raise ValueError("on_click must reference a function name or None") from exc
                if isinstance(expr_ast, ast.Constant) and expr_ast.value is None:
                    callback_name = None
                elif isinstance(expr_ast, ast.Name):
                    callback_name = expr_ast.id
                else:
                    raise ValueError("on_click must reference a function name or None")

            button_names.add(name)
            button_pins[name] = pin_value
            if callback_name is not None:
                button_callbacks[name] = callback_name
            vars[name] = _ExprStr(name)
            button_poll_names.add(name)
            ctx["button_force_loop"] = True
            body.append(
                ButtonDecl(
                    name=name,
                    pin=pin_value,
                    on_click=callback_name,
                )
            )
            i += 1
            continue

        # --- IMPORTANT: handle assignments FIRST (single + tuple) ---
        # This updates env before we evaluate Led(...) or sleep(...)
        assignment_nodes = _handle_assignment_ast(line, ctx, scope, depth)
        if assignment_nodes is not None:
            body.extend(assignment_nodes)
            i += 1
            continue

        m = RE_IF.match(line)
        if m:
            base_indent = _indent_of(raw)
            cond_expr = _to_c_expr(m.group(1), vars, ctx)
            block, next_idx = _collect_block(snippet, i)
            base_ctx_vars = dict(vars)
            base_types = dict(ctx.get("var_types", {}))
            base_declared = set(ctx.get("var_declared", set()))
            def _branch_ctx() -> Dict[str, object]:
                child = dict(ctx)
                child["vars"] = dict(base_ctx_vars)
                child["var_types"] = dict(base_types)
                child["var_declared"] = set(base_declared)
                child["_base_declared"] = set(base_declared)
                child["globals"] = ctx.setdefault("globals", [])
                helpers_set = ctx.setdefault("helpers", set())
                child["helpers"] = helpers_set
                child["vars"].setdefault("_helpers", helpers_set)
                if "tmp_counter" in ctx:
                    child["tmp_counter"] = ctx["tmp_counter"]
                return child
            branch_entries: List[Tuple[Dict[str, object], List[object]]] = []
            first_ctx = _branch_ctx()
            first_body = _parse_simple_lines(
                block,
                first_ctx,
                scope,
                depth + 1,
                loop_depth=loop_depth,
                main_loop=main_loop,
            )
            branch_entries.append((first_ctx, first_body))

            branches: List[ConditionalBranch] = [
                ConditionalBranch(condition=cond_expr, body=first_body)
            ]
            else_body: List[object] = []
            else_entry: Optional[Tuple[Dict[str, object], List[object]]] = None
            j = next_idx
            while j < len(snippet):
                probe_raw = snippet[j]
                probe_text = probe_raw.strip()
                if not probe_text:
                    j += 1
                    continue
                if _indent_of(probe_raw) != base_indent:
                    break
                m_elif = RE_ELIF.match(probe_text)
                if m_elif:
                    cond = _to_c_expr(m_elif.group(1), vars, ctx)
                    elif_block, j = _collect_block(snippet, j)
                    elif_ctx = _branch_ctx()
                    elif_body = _parse_simple_lines(
                        elif_block,
                        elif_ctx,
                        scope,
                        depth + 1,
                        loop_depth=loop_depth,
                        main_loop=main_loop,
                    )
                    branch_entries.append((elif_ctx, elif_body))
                    branches.append(ConditionalBranch(condition=cond, body=elif_body))
                    continue
                if RE_ELSE.match(probe_text):
                    else_block, j = _collect_block(snippet, j)
                    else_ctx = _branch_ctx()
                    else_body = _parse_simple_lines(
                        else_block,
                        else_ctx,
                        scope,
                        depth + 1,
                        loop_depth=loop_depth,
                        main_loop=main_loop,
                    )
                    else_entry = (else_ctx, else_body)
                    break
                break
            promoted_names = _promote_branch_decls(
                branch_entries,
                else_entry,
                ctx,
                scope,
                depth,
            )

            if promoted_names:
                def _rewrite(nodes: List[object]) -> List[object]:
                    rewritten: List[object] = []
                    for node in nodes:
                        if isinstance(node, VarDecl) and node.name in promoted_names:
                            rewritten.append(VarAssign(name=node.name, expr=node.expr))
                            continue
                        if isinstance(node, IfStatement):
                            new_branches = [
                                ConditionalBranch(
                                    condition=b.condition,
                                    body=_rewrite(b.body),
                                )
                                for b in node.branches
                            ]
                            new_else = _rewrite(node.else_body)
                            rewritten.append(
                                IfStatement(branches=new_branches, else_body=new_else)
                            )
                            continue
                        rewritten.append(node)
                    return rewritten

                for idx, branch in enumerate(branches):
                    branch.body = _rewrite(branch_entries[idx][1])
                if else_entry is not None:
                    else_body = _rewrite(else_body)

            body.extend(
                _make_promotion_decls(promoted_names, ctx, scope, depth)
            )
            body.append(IfStatement(branches=branches, else_body=else_body))
            i = j
            continue

        m = RE_TRY.match(line)
        if m:
            base_indent = _indent_of(raw)
            try_block, next_idx = _collect_block(snippet, i)

            base_ctx_vars = dict(vars)
            base_types = dict(ctx.get("var_types", {}))
            base_declared = set(ctx.get("var_declared", set()))

            def _child_ctx() -> Dict[str, object]:
                child = dict(ctx)
                child["vars"] = dict(base_ctx_vars)
                child["var_types"] = dict(base_types)
                child["var_declared"] = set(base_declared)
                child["_base_declared"] = set(base_declared)
                child["globals"] = ctx.setdefault("globals", [])
                helpers_set = ctx.setdefault("helpers", set())
                child["helpers"] = helpers_set
                child["vars"].setdefault("_helpers", helpers_set)
                if "tmp_counter" in ctx:
                    child["tmp_counter"] = ctx["tmp_counter"]
                return child

            branch_entries: List[Tuple[Dict[str, object], List[object]]] = []
            handler_entries: List[Tuple[Dict[str, object], CatchClause]] = []

            try_ctx = _child_ctx()
            try_body = _parse_simple_lines(
                try_block,
                try_ctx,
                scope,
                depth + 1,
                loop_depth=loop_depth,
                main_loop=main_loop,
            )
            branch_entries.append((try_ctx, try_body))

            handlers: List[CatchClause] = []
            j = next_idx

            while j < len(snippet):
                probe_raw = snippet[j]
                probe_text = probe_raw.strip()
                if not probe_text:
                    j += 1
                    continue
                if _indent_of(probe_raw) != base_indent:
                    break
                m_except = RE_EXCEPT.match(probe_text)
                if m_except:
                    except_block, j = _collect_block(snippet, j)
                    except_ctx = _child_ctx()
                    except_body = _parse_simple_lines(
                        except_block,
                        except_ctx,
                        scope,
                        depth + 1,
                        loop_depth=loop_depth,
                        main_loop=main_loop,
                    )
                    handler = CatchClause(
                        exception=m_except.group(1),
                        target=m_except.group(2),
                        body=except_body,
                    )
                    handlers.append(handler)
                    branch_entries.append((except_ctx, except_body))
                    handler_entries.append((except_ctx, handler))
                    continue
                break

            promoted_names = _promote_branch_decls(
                branch_entries,
                None,
                ctx,
                scope,
                depth,
            )

            if promoted_names:
                promoted_set = set(promoted_names)
                try_body = _rewrite_nodes(try_body, promoted_set)
                for child_ctx, handler in handler_entries:
                    handler.body = _rewrite_nodes(handler.body, promoted_set)
                body.extend(_make_promotion_decls(promoted_names, ctx, scope, depth))

            if "tmp_counter" in try_ctx:
                ctx["tmp_counter"] = max(
                    ctx.get("tmp_counter", 0), try_ctx["tmp_counter"]
                )
            for child_ctx, _handler in handler_entries:
                if "tmp_counter" in child_ctx:
                    ctx["tmp_counter"] = max(
                        ctx.get("tmp_counter", 0), child_ctx["tmp_counter"]
                    )

            body.append(TryStatement(try_body=try_body, handlers=handlers))
            i = j
            continue

        m = RE_WHILE.match(line)
        if m:
            cond_expr = _to_c_expr(m.group(1), vars, ctx)
            block, next_idx = _collect_block(snippet, i)
            child_ctx: Dict[str, object] = dict(ctx)
            child_ctx["vars"] = dict(vars)
            child_ctx["var_types"] = dict(ctx.get("var_types", {}))
            base_declared = set(ctx.get("var_declared", set()))
            child_ctx["var_declared"] = set(base_declared)
            child_ctx["_base_declared"] = set(base_declared)
            child_ctx["globals"] = ctx.setdefault("globals", [])
            helpers_set = ctx.setdefault("helpers", set())
            child_ctx["helpers"] = helpers_set
            child_ctx["vars"].setdefault("_helpers", helpers_set)
            if "tmp_counter" in ctx:
                child_ctx["tmp_counter"] = ctx["tmp_counter"]

            loop_body = _parse_simple_lines(
                block,
                child_ctx,
                scope,
                depth + 1,
                loop_depth=loop_depth + 1,
                main_loop=main_loop,
            )

            promoted_set = {
                name
                for name in child_ctx.get("var_declared", set())
                if name not in child_ctx.get("_base_declared", set())
            }

            promoted_names: List[str] = []

            def _collect_order(nodes: List[object]) -> None:
                for inner in nodes:
                    if isinstance(inner, VarDecl) and inner.name in promoted_set:
                        if inner.name not in promoted_names:
                            promoted_names.append(inner.name)
                        continue
                    if isinstance(inner, IfStatement):
                        for branch in inner.branches:
                            _collect_order(branch.body)
                        _collect_order(inner.else_body)
                        continue
                    if isinstance(inner, WhileLoop):
                        _collect_order(inner.body)
                        continue
                    if isinstance(inner, ForRangeLoop):
                        _collect_order(inner.body)

            _collect_order(loop_body)

            for name in promoted_set:
                if name not in promoted_names:
                    promoted_names.append(name)

            if promoted_names:
                var_types = ctx.setdefault("var_types", {})
                child_types = child_ctx.get("var_types", {})
                for name in promoted_names:
                    var_types[name] = child_types.get(name, "int")
                body.extend(
                    _make_promotion_decls(promoted_names, ctx, scope, depth)
                )
                loop_body = _rewrite_nodes(loop_body, set(promoted_names))

            if "tmp_counter" in child_ctx:
                ctx["tmp_counter"] = child_ctx["tmp_counter"]

            body.append(WhileLoop(condition=cond_expr, body=loop_body))
            i = next_idx
            continue

        m = RE_FOR_RANGE.match(line)
        if m:
            var_name = m.group(1)
            args_src = m.group(2)
            count_arg = _extract_call_argument(args_src, position=0)
            extra_arg = _extract_call_argument(args_src, position=1)
            if count_arg is None or extra_arg is not None:
                raise ValueError("for-range loops require a single range(count) argument")
            count = _resolve_numeric_arg(count_arg, 0)
            block, next_idx = _collect_block(snippet, i)
            child_ctx = dict(ctx)
            child_ctx["vars"] = dict(vars)
            child_ctx["var_types"] = dict(ctx.get("var_types", {}))
            base_declared = set(ctx.get("var_declared", set()))
            base_with_loop_var = set(base_declared)
            base_with_loop_var.add(var_name)
            child_ctx["var_declared"] = set(base_with_loop_var)
            child_ctx["_base_declared"] = set(base_with_loop_var)
            child_ctx["globals"] = ctx.setdefault("globals", [])
            helpers_set = ctx.setdefault("helpers", set())
            child_ctx["helpers"] = helpers_set
            child_ctx["vars"].setdefault("_helpers", helpers_set)
            if "tmp_counter" in ctx:
                child_ctx["tmp_counter"] = ctx["tmp_counter"]

            child_ctx["vars"][var_name] = _ExprStr(var_name)
            child_ctx["var_types"][var_name] = "int"

            loop_body = _parse_simple_lines(
                block,
                child_ctx,
                scope,
                depth + 1,
                loop_depth=loop_depth + 1,
                main_loop=main_loop,
            )

            promoted_set = {
                name
                for name in child_ctx.get("var_declared", set())
                if name not in child_ctx.get("_base_declared", set())
            }

            promoted_names: List[str] = []

            def _collect_order(nodes: List[object]) -> None:
                for inner in nodes:
                    if isinstance(inner, VarDecl) and inner.name in promoted_set:
                        if inner.name not in promoted_names:
                            promoted_names.append(inner.name)
                        continue
                    if isinstance(inner, IfStatement):
                        for branch in inner.branches:
                            _collect_order(branch.body)
                        _collect_order(inner.else_body)
                        continue
                    if isinstance(inner, WhileLoop):
                        _collect_order(inner.body)
                        continue
                    if isinstance(inner, ForRangeLoop):
                        _collect_order(inner.body)

            _collect_order(loop_body)

            for name in promoted_set:
                if name not in promoted_names:
                    promoted_names.append(name)

            if promoted_names:
                var_types = ctx.setdefault("var_types", {})
                child_types = child_ctx.get("var_types", {})
                for name in promoted_names:
                    var_types[name] = child_types.get(name, "int")
                body.extend(
                    _make_promotion_decls(promoted_names, ctx, scope, depth)
                )
                loop_body = _rewrite_nodes(loop_body, set(promoted_names))

            if "tmp_counter" in child_ctx:
                ctx["tmp_counter"] = child_ctx["tmp_counter"]

            body.append(
                ForRangeLoop(var_name=var_name, count=count, body=loop_body)
            )
            i = next_idx
            continue

        # Led declaration with expression (uses env updated above)
        m = RE_LCD_DECL.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            interface = "parallel"
            i2c_arg = _extract_call_argument(args_src, keyword="i2c_addr")
            cols_arg = _extract_call_argument(args_src, keyword="cols")
            rows_arg = _extract_call_argument(args_src, keyword="rows")
            backlight_arg = _extract_call_argument(args_src, keyword="backlight_pin")
            rw_arg = _extract_call_argument(args_src, keyword="rw")
            if i2c_arg is not None and i2c_arg.strip():
                interface = "i2c"
            cols_value = _resolve_numeric_arg(cols_arg, 16)
            rows_value = _resolve_numeric_arg(rows_arg, 2)
            backlight_value = _resolve_optional_numeric_arg(backlight_arg)
            if interface == "i2c":
                i2c_value = _resolve_numeric_arg(i2c_arg, 0)
                lcd_names.add(name)
                vars[name] = _ExprStr(name)
                body.append(
                    LCDDecl(
                        name=name,
                        cols=cols_value,
                        rows=rows_value,
                        interface="i2c",
                        i2c_addr=i2c_value,
                        backlight_pin=backlight_value,
                    )
                )
                i += 1
                continue

            rs_arg = _extract_call_argument(args_src, keyword="rs")
            en_arg = _extract_call_argument(args_src, keyword="en")
            d4_arg = _extract_call_argument(args_src, keyword="d4")
            d5_arg = _extract_call_argument(args_src, keyword="d5")
            d6_arg = _extract_call_argument(args_src, keyword="d6")
            d7_arg = _extract_call_argument(args_src, keyword="d7")
            if rs_arg is None:
                rs_arg = _extract_call_argument(args_src, position=0)
            if en_arg is None:
                en_arg = _extract_call_argument(args_src, position=1)
            if d4_arg is None:
                d4_arg = _extract_call_argument(args_src, position=2)
            if d5_arg is None:
                d5_arg = _extract_call_argument(args_src, position=3)
            if d6_arg is None:
                d6_arg = _extract_call_argument(args_src, position=4)
            if d7_arg is None:
                d7_arg = _extract_call_argument(args_src, position=5)
            if cols_arg is None:
                cols_pos = _extract_call_argument(args_src, position=6)
                if cols_pos is not None:
                    cols_value = _resolve_numeric_arg(cols_pos, 16)
            if rows_arg is None:
                rows_pos = _extract_call_argument(args_src, position=7)
                if rows_pos is not None:
                    rows_value = _resolve_numeric_arg(rows_pos, 2)
            if not all(arg and arg.strip() for arg in (rs_arg, en_arg, d4_arg, d5_arg, d6_arg, d7_arg)):
                raise ValueError("LCD parallel mode requires rs, en, d4, d5, d6 and d7 pins")
            rw_value = _resolve_optional_numeric_arg(rw_arg)
            lcd_names.add(name)
            vars[name] = _ExprStr(name)
            body.append(
                LCDDecl(
                    name=name,
                    cols=cols_value,
                    rows=rows_value,
                    interface="parallel",
                    rs=_resolve_numeric_arg(rs_arg, 0),
                    en=_resolve_numeric_arg(en_arg, 0),
                    d4=_resolve_numeric_arg(d4_arg, 0),
                    d5=_resolve_numeric_arg(d5_arg, 0),
                    d6=_resolve_numeric_arg(d6_arg, 0),
                    d7=_resolve_numeric_arg(d7_arg, 0),
                    rw=rw_value,
                    backlight_pin=backlight_value,
                )
            )
            i += 1
            continue

        m = RE_LED_DECL.match(line)
        if m:
            name, expr = m.group(1), m.group(2)
            arg_expr = _extract_call_argument(expr, keyword="pin")
            if arg_expr is None:
                arg_expr = _extract_call_argument(expr)
            if arg_expr is None or not arg_expr.strip():
                body.append(LedDecl(name=name, pin=13))
                ctx.setdefault("led_names", set()).add(name)
                i += 1
                continue
            try:
                expr_ast = ast.parse(arg_expr, mode="eval").body
            except Exception:
                expr_ast = None
            if expr_ast is not None and not _expr_has_name(expr_ast):
                try:
                    pin_val = int(_eval_const(arg_expr, vars))
                    body.append(LedDecl(name=name, pin=pin_val))
                    ctx.setdefault("led_names", set()).add(name)
                    i += 1
                    continue
                except Exception:
                    pass
            pin_expr = _to_c_expr(arg_expr, vars, ctx)
            body.append(LedDecl(name=name, pin=pin_expr))
            ctx.setdefault("led_names", set()).add(name)
            i += 1
            continue

        m = RE_BUZZER_DECL.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            pin_arg = _extract_call_argument(args_src, keyword="pin")
            if pin_arg is None:
                pin_arg = _extract_call_argument(args_src)
            pin_value: Union[int, str] = 8
            if pin_arg and pin_arg.strip():
                try:
                    expr_ast = ast.parse(pin_arg, mode="eval").body
                except Exception:
                    expr_ast = None
                handled = False
                if expr_ast is not None and not _expr_has_name(expr_ast):
                    try:
                        value = _eval_const(pin_arg, vars)
                    except Exception:
                        pass
                    else:
                        if isinstance(value, bool):
                            pin_value = 1 if value else 0
                            handled = True
                        elif isinstance(value, (int, float)):
                            pin_value = int(value)
                            handled = True
                if not handled:
                    pin_value = _to_c_expr(pin_arg, vars, ctx)

            default_arg = _extract_call_argument(args_src, keyword="default_frequency")
            default_frequency: Union[float, int, str] = 440.0
            if default_arg and default_arg.strip():
                default_frequency = _resolve_float_arg(default_arg, 440.0)

            body.append(
                BuzzerDecl(
                    name=name,
                    pin=pin_value,
                    default_frequency=default_frequency,
                )
            )
            buzzer_names.add(name)
            i += 1
            continue

        m = RE_SERVO_DECL.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            pin_arg = _extract_call_argument(args_src, keyword="pin")
            if pin_arg is None:
                pin_arg = _extract_call_argument(args_src)
            pin_value: Union[int, str] = 9
            if pin_arg and pin_arg.strip():
                handled = False
                try:
                    expr_ast = ast.parse(pin_arg, mode="eval").body
                except Exception:
                    expr_ast = None
                if expr_ast is not None and not _expr_has_name(expr_ast):
                    try:
                        value = _eval_const(pin_arg, vars)
                    except Exception:
                        pass
                    else:
                        if isinstance(value, bool):
                            pin_value = 1 if value else 0
                            handled = True
                        elif isinstance(value, (int, float)):
                            pin_value = int(value)
                            handled = True
                if not handled:
                    pin_value = _to_c_expr(pin_arg, vars, ctx)

            min_angle_arg = _extract_call_argument(args_src, keyword="min_angle")
            max_angle_arg = _extract_call_argument(args_src, keyword="max_angle")
            min_pulse_arg = _extract_call_argument(args_src, keyword="min_pulse_us")
            max_pulse_arg = _extract_call_argument(args_src, keyword="max_pulse_us")

            min_angle = _resolve_float_arg(min_angle_arg, 0.0)
            max_angle = _resolve_float_arg(max_angle_arg, 180.0)
            min_pulse = _resolve_numeric_arg(min_pulse_arg, 544)
            max_pulse = _resolve_numeric_arg(max_pulse_arg, 2400)

            if (
                isinstance(min_angle, (int, float))
                and isinstance(max_angle, (int, float))
                and float(min_angle) >= float(max_angle)
            ):
                raise ValueError("min_angle must be smaller than max_angle")
            if (
                isinstance(min_pulse, int)
                and isinstance(max_pulse, int)
                and min_pulse >= max_pulse
            ):
                raise ValueError("min_pulse_us must be smaller than max_pulse_us")

            servo_names.add(name)
            vars[name] = _ExprStr(name)
            body.append(
                ServoDecl(
                    name=name,
                    pin=pin_value,
                    min_angle=min_angle,
                    max_angle=max_angle,
                    min_pulse_us=min_pulse,
                    max_pulse_us=max_pulse,
                )
            )
            i += 1
            continue

        m = RE_RGB_LED_DECL.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            red_arg = _extract_call_argument(args_src, keyword="red_pin")
            if red_arg is None:
                red_arg = _extract_call_argument(args_src)
            green_arg = _extract_call_argument(args_src, keyword="green_pin")
            if green_arg is None:
                green_arg = _extract_call_argument(args_src, position=1)
            blue_arg = _extract_call_argument(args_src, keyword="blue_pin")
            if blue_arg is None:
                blue_arg = _extract_call_argument(args_src, position=2)
            if not red_arg or not green_arg or not blue_arg:
                raise ValueError("RGBLed requires red, green, and blue pins")

            def _resolve_rgb_pin(src_text: str) -> Union[int, str]:
                text = src_text.strip()
                try:
                    expr_ast = ast.parse(text, mode="eval").body
                except Exception:
                    expr_ast = None
                if expr_ast is not None and not _expr_has_name(expr_ast):
                    try:
                        value = _eval_const(text, vars)
                    except Exception:
                        pass
                    else:
                        if isinstance(value, bool):
                            return 1 if value else 0
                        if isinstance(value, (int, float)):
                            return int(value)
                return _to_c_expr(text, vars, ctx)

            red_value = _resolve_rgb_pin(red_arg)
            green_value = _resolve_rgb_pin(green_arg)
            blue_value = _resolve_rgb_pin(blue_arg)
            body.append(
                RGBLedDecl(
                    name=name,
                    red_pin=red_value,
                    green_pin=green_value,
                    blue_pin=blue_value,
                )
            )
            rgb_led_names.add(name)
            i += 1
            continue

        m = RE_ULTRASONIC_DECL.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            trig_arg = _extract_call_argument(args_src, keyword="trig")
            if trig_arg is None:
                trig_arg = _extract_call_argument(args_src)
            echo_arg = _extract_call_argument(args_src, keyword="echo")
            if echo_arg is None:
                echo_arg = _extract_call_argument(args_src, position=1)
            if trig_arg is None or not trig_arg.strip():
                raise ValueError("Ultrasonic sensors require a trig pin")
            if echo_arg is None or not echo_arg.strip():
                raise ValueError("Ultrasonic sensors require an echo pin")

            def _resolve_pin(src_text: str) -> Union[int, str]:
                text = src_text.strip()
                try:
                    expr_ast = ast.parse(text, mode="eval").body
                except Exception:
                    expr_ast = None
                if expr_ast is not None and not _expr_has_name(expr_ast):
                    try:
                        value = _eval_const(text, vars)
                    except Exception:
                        pass
                    else:
                        if isinstance(value, bool):
                            return 1 if value else 0
                        if isinstance(value, (int, float)):
                            return int(value)
                return _to_c_expr(text, vars, ctx)

            trig_value = _resolve_pin(trig_arg)
            echo_value = _resolve_pin(echo_arg)

            model_arg = _extract_call_argument(args_src, keyword="sensor")
            if model_arg is None:
                model_arg = _extract_call_argument(args_src, keyword="model")
            model = "HC-SR04"
            if model_arg is not None and model_arg.strip():
                try:
                    resolved = _eval_const(model_arg, vars)
                except Exception:
                    try:
                        resolved = ast.literal_eval(model_arg)
                    except Exception as exc:  # pragma: no cover - defensive
                        raise ValueError("Ultrasonic sensor type must be a literal string") from exc
                if isinstance(resolved, _ExprStr):
                    raise ValueError("Ultrasonic sensor type must be a literal string")
                if not isinstance(resolved, str):
                    raise ValueError("Ultrasonic sensor type must be a string literal")
                canonical = resolved.strip().upper().replace("_", "-")
                if canonical != "HC-SR04":
                    raise ValueError(f"Unsupported ultrasonic sensor '{resolved}'")
                model = "HC-SR04"

            vars[name] = _ExprStr(name)
            ctx.setdefault("ultrasonic_names", set()).add(name)
            ctx.setdefault("ultrasonic_models", {})[name] = model
            ctx.setdefault("ultrasonic_measure_calls", set())
            body.append(UltrasonicDecl(name=name, trig=trig_value, echo=echo_value, model=model))
            i += 1
            continue

        m = RE_SERIAL_DECL.match(line)
        if m:
            name, expr = m.group(1), m.group(2)
            baud_arg = _extract_call_argument(expr, keyword="baud_rate")
            if baud_arg is None:
                baud_arg = _extract_call_argument(expr)
            baud_value: Union[int, str] = 9600
            if baud_arg is not None and baud_arg.strip():
                try:
                    expr_ast = ast.parse(baud_arg, mode="eval").body
                except Exception:
                    expr_ast = None
                if expr_ast is not None and not _expr_has_name(expr_ast):
                    try:
                        baud_value = int(_eval_const(baud_arg, vars))
                    except Exception:
                        baud_value = _to_c_expr(baud_arg, vars, ctx)
                else:
                    baud_value = _to_c_expr(baud_arg, vars, ctx)
            body.append(SerialMonitorDecl(name=name, baud=baud_value))
            ctx.setdefault("serial_monitors", set()).add(name)
            vars[name] = _ExprStr(name)
            i += 1
            continue

        # Actions
        m = RE_RGB_LED_SET_COLOR.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in rgb_led_names:
                red_arg = _extract_call_argument(args_src, keyword="red")
                if red_arg is None:
                    red_arg = _extract_call_argument(args_src)
                green_arg = _extract_call_argument(args_src, keyword="green")
                if green_arg is None:
                    green_arg = _extract_call_argument(args_src, position=1)
                blue_arg = _extract_call_argument(args_src, keyword="blue")
                if blue_arg is None:
                    blue_arg = _extract_call_argument(args_src, position=2)
                if red_arg is None or green_arg is None or blue_arg is None:
                    raise ValueError("set_color requires red, green, and blue components")
                red_value = _resolve_numeric_arg(red_arg, 0)
                green_value = _resolve_numeric_arg(green_arg, 0)
                blue_value = _resolve_numeric_arg(blue_arg, 0)
                body.append(
                    RGBLedSetColor(
                        name=name,
                        red=red_value,
                        green=green_value,
                        blue=blue_value,
                    )
                )
                i += 1
                continue

        m = RE_RGB_LED_ON.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in rgb_led_names:
                red_arg = _extract_call_argument(args_src)
                green_arg = _extract_call_argument(args_src, position=1)
                blue_arg = _extract_call_argument(args_src, position=2)
                red_value = _resolve_numeric_arg(red_arg, 255)
                green_value = _resolve_numeric_arg(green_arg, 255)
                blue_value = _resolve_numeric_arg(blue_arg, 255)
                body.append(
                    RGBLedOn(
                        name=name,
                        red=red_value,
                        green=green_value,
                        blue=blue_value,
                    )
                )
                i += 1
                continue

        m = RE_RGB_LED_OFF.match(line)
        if m:
            name = m.group(1)
            if name in rgb_led_names:
                body.append(RGBLedOff(name=name))
                i += 1
                continue

        m = RE_RGB_LED_FADE.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in rgb_led_names:
                red_arg = _extract_call_argument(args_src, keyword="red")
                if red_arg is None:
                    red_arg = _extract_call_argument(args_src)
                green_arg = _extract_call_argument(args_src, keyword="green")
                if green_arg is None:
                    green_arg = _extract_call_argument(args_src, position=1)
                blue_arg = _extract_call_argument(args_src, keyword="blue")
                if blue_arg is None:
                    blue_arg = _extract_call_argument(args_src, position=2)
                if red_arg is None or green_arg is None or blue_arg is None:
                    raise ValueError("fade requires red, green, and blue components")
                duration_arg = _extract_call_argument(args_src, keyword="duration_ms")
                if duration_arg is None:
                    duration_arg = _extract_call_argument(args_src, position=3)
                steps_arg = _extract_call_argument(args_src, keyword="steps")
                if steps_arg is None:
                    steps_arg = _extract_call_argument(args_src, position=4)
                body.append(
                    RGBLedFade(
                        name=name,
                        red=_resolve_numeric_arg(red_arg, 0),
                        green=_resolve_numeric_arg(green_arg, 0),
                        blue=_resolve_numeric_arg(blue_arg, 0),
                        duration_ms=_resolve_numeric_arg(duration_arg, 1000),
                        steps=_resolve_numeric_arg(steps_arg, 50),
                    )
                )
                i += 1
                continue

        m = RE_RGB_LED_BLINK.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in rgb_led_names:
                red_arg = _extract_call_argument(args_src, keyword="red")
                if red_arg is None:
                    red_arg = _extract_call_argument(args_src)
                green_arg = _extract_call_argument(args_src, keyword="green")
                if green_arg is None:
                    green_arg = _extract_call_argument(args_src, position=1)
                blue_arg = _extract_call_argument(args_src, keyword="blue")
                if blue_arg is None:
                    blue_arg = _extract_call_argument(args_src, position=2)
                if red_arg is None or green_arg is None or blue_arg is None:
                    raise ValueError("blink requires red, green, and blue components")
                times_arg = _extract_call_argument(args_src, keyword="times")
                if times_arg is None:
                    times_arg = _extract_call_argument(args_src, position=3)
                delay_arg = _extract_call_argument(args_src, keyword="delay_ms")
                if delay_arg is None:
                    delay_arg = _extract_call_argument(args_src, position=4)
                body.append(
                    RGBLedBlink(
                        name=name,
                        red=_resolve_numeric_arg(red_arg, 0),
                        green=_resolve_numeric_arg(green_arg, 0),
                        blue=_resolve_numeric_arg(blue_arg, 0),
                        times=_resolve_numeric_arg(times_arg, 1),
                        delay_ms=_resolve_numeric_arg(delay_arg, 200),
                    )
                )
                i += 1
                continue

        m = RE_LED_ON.match(line)
        if m:
            body.append(LedOn(name=m.group(1)))
            i += 1
            continue

        m = RE_LED_OFF.match(line)
        if m:
            body.append(LedOff(name=m.group(1)))
            i += 1
            continue

        m = RE_LED_TOGGLE.match(line)
        if m:
            body.append(LedToggle(name=m.group(1)))
            i += 1
            continue

        m = RE_LED_SET_BRIGHTNESS.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            value_arg = _extract_call_argument(args_src, keyword="value")
            if value_arg is None:
                value_arg = _extract_call_argument(args_src)
            value = _resolve_numeric_arg(value_arg, 0)
            body.append(LedSetBrightness(name=name, value=value))
            i += 1
            continue

        m = RE_LED_BLINK.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            duration_arg = _extract_call_argument(args_src, keyword="duration_ms")
            if duration_arg is None:
                duration_arg = _extract_call_argument(args_src)
            times_arg = _extract_call_argument(args_src, keyword="times")
            if times_arg is None:
                times_arg = _extract_call_argument(args_src, position=1)
            duration = _resolve_numeric_arg(duration_arg, 0)
            times = _resolve_numeric_arg(times_arg, 1)
            body.append(LedBlink(name=name, duration_ms=duration, times=times))
            i += 1
            continue

        m = RE_LED_FADE_IN.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            step_arg = _extract_call_argument(args_src, keyword="step")
            if step_arg is None:
                step_arg = _extract_call_argument(args_src)
            delay_arg = _extract_call_argument(args_src, keyword="delay_ms")
            if delay_arg is None:
                delay_arg = _extract_call_argument(args_src, position=1)
            step = _resolve_numeric_arg(step_arg, 5)
            delay_val = _resolve_numeric_arg(delay_arg, 10)
            body.append(LedFadeIn(name=name, step=step, delay_ms=delay_val))
            i += 1
            continue

        m = RE_LED_FADE_OUT.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            step_arg = _extract_call_argument(args_src, keyword="step")
            if step_arg is None:
                step_arg = _extract_call_argument(args_src)
            delay_arg = _extract_call_argument(args_src, keyword="delay_ms")
            if delay_arg is None:
                delay_arg = _extract_call_argument(args_src, position=1)
            step = _resolve_numeric_arg(step_arg, 5)
            delay_val = _resolve_numeric_arg(delay_arg, 10)
            body.append(LedFadeOut(name=name, step=step, delay_ms=delay_val))
            i += 1
            continue

        m = RE_LED_FLASH_PATTERN.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            pattern_arg = _extract_call_argument(args_src, keyword="pattern")
            if pattern_arg is None:
                pattern_arg = _extract_call_argument(args_src)
            delay_arg = _extract_call_argument(args_src, keyword="delay_ms")
            if delay_arg is None:
                delay_arg = _extract_call_argument(args_src, position=1)
            pattern_values: List[int] = []
            if pattern_arg and pattern_arg.strip():
                pattern_src = pattern_arg.strip()

                def _coerce_pattern(value: object) -> None:
                    if not isinstance(value, (list, tuple)):
                        raise ValueError("flash_pattern requires a literal pattern list")
                    for entry in value:
                        if isinstance(entry, bool):
                            pattern_values.append(1 if entry else 0)
                        elif isinstance(entry, (int, float)):
                            pattern_values.append(int(entry))
                        else:
                            raise ValueError("flash_pattern values must be numeric")

                resolved: Optional[object] = None
                try:
                    resolved = ast.literal_eval(pattern_src)
                except Exception:
                    try:
                        expr_node = ast.parse(pattern_src, mode="eval").body
                    except Exception as exc:  # pragma: no cover - defensive
                        raise ValueError("flash_pattern requires a literal pattern list") from exc
                    if isinstance(expr_node, ast.Name):
                        var_name = expr_node.id
                        value = vars.get(var_name)
                        if isinstance(value, _ExprStr):
                            raise ValueError("flash_pattern requires a literal pattern list")
                        resolved = value
                    if resolved is None:
                        raise ValueError("flash_pattern requires a literal pattern list")
                else:
                    _coerce_pattern(resolved)
                    resolved = None

                if resolved is not None:
                    _coerce_pattern(resolved)
            delay_val = _resolve_numeric_arg(delay_arg, 200)
            body.append(LedFlashPattern(name=name, pattern=pattern_values, delay_ms=delay_val))
            i += 1
            continue

        m = RE_BUZZER_PLAY_TONE.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            freq_arg = _extract_call_argument(args_src, keyword="frequency")
            freq_from_position = False
            if freq_arg is None:
                freq_arg = _extract_call_argument(args_src)
                if freq_arg is not None:
                    freq_from_position = True
            if freq_arg is None or not freq_arg.strip():
                raise ValueError("play_tone requires a frequency")
            frequency = _resolve_float_arg(freq_arg, 0.0)
            duration_arg = _extract_call_argument(args_src, keyword="duration_ms")
            if duration_arg is None:
                pos_index = 1 if freq_from_position else 0
                duration_arg = _extract_call_argument(args_src, position=pos_index)
            duration: Optional[Union[float, int, str]] = None
            if duration_arg is not None and duration_arg.strip():
                duration = _resolve_float_arg(duration_arg, 0.0)
            body.append(
                BuzzerPlayTone(name=name, frequency=frequency, duration_ms=duration)
            )
            i += 1
            continue

        m = RE_BUZZER_STOP.match(line)
        if m:
            body.append(BuzzerStop(name=m.group(1)))
            i += 1
            continue

        m = RE_BUZZER_BEEP.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            freq_arg = _extract_call_argument(args_src, keyword="frequency")
            freq_from_position = False
            if freq_arg is None:
                freq_arg = _extract_call_argument(args_src)
                if freq_arg is not None:
                    freq_from_position = True
            frequency: Optional[Union[float, int, str]] = None
            if freq_arg is not None and freq_arg.strip():
                frequency = _resolve_float_arg(freq_arg, 0.0)
            on_arg = _extract_call_argument(args_src, keyword="on_ms")
            if on_arg is None:
                position = 1 if freq_from_position else 0
                on_arg = _extract_call_argument(args_src, position=position)
            off_arg = _extract_call_argument(args_src, keyword="off_ms")
            if off_arg is None:
                position = 2 if freq_from_position else 1
                off_arg = _extract_call_argument(args_src, position=position)
            times_arg = _extract_call_argument(args_src, keyword="times")
            if times_arg is None:
                position = 3 if freq_from_position else 2
                times_arg = _extract_call_argument(args_src, position=position)
            on_ms = _resolve_float_arg(on_arg, 100) if on_arg else 100
            off_ms = _resolve_float_arg(off_arg, 100) if off_arg else 100
            times = _resolve_numeric_arg(times_arg, 1)
            body.append(
                BuzzerBeep(
                    name=name,
                    frequency=frequency,
                    on_ms=on_ms,
                    off_ms=off_ms,
                    times=times,
                )
            )
            i += 1
            continue

        m = RE_BUZZER_SWEEP.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            start_arg = _extract_call_argument(args_src, keyword="start_hz")
            if start_arg is None:
                start_arg = _extract_call_argument(args_src)
            if start_arg is None or not start_arg.strip():
                raise ValueError("sweep requires a start frequency")
            end_arg = _extract_call_argument(args_src, keyword="end_hz")
            if end_arg is None:
                end_arg = _extract_call_argument(args_src, position=1)
            if end_arg is None or not end_arg.strip():
                raise ValueError("sweep requires an end frequency")
            duration_arg = _extract_call_argument(args_src, keyword="duration_ms")
            if duration_arg is None:
                duration_arg = _extract_call_argument(args_src, position=2)
            if duration_arg is None or not duration_arg.strip():
                raise ValueError("sweep requires duration_ms")
            steps_arg = _extract_call_argument(args_src, keyword="steps")
            if steps_arg is None:
                steps_arg = _extract_call_argument(args_src, position=3)
            start_val = _resolve_float_arg(start_arg, 0.0)
            end_val = _resolve_float_arg(end_arg, 0.0)
            duration_val = _resolve_float_arg(duration_arg, 0.0)
            steps_val = _resolve_numeric_arg(steps_arg, 10)
            body.append(
                BuzzerSweep(
                    name=name,
                    start_hz=start_val,
                    end_hz=end_val,
                    duration_ms=duration_val,
                    steps=steps_val,
                )
            )
            i += 1
            continue

        m = RE_BUZZER_MELODY.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            melody_arg = _extract_call_argument(args_src, keyword="name")
            if melody_arg is None:
                melody_arg = _extract_call_argument(args_src)
            if melody_arg is None or not melody_arg.strip():
                raise ValueError("melody requires a name")
            try:
                melody_ast = ast.parse(melody_arg, mode="eval").body
            except Exception as exc:
                raise ValueError("melody name must be a string literal") from exc
            if not (
                isinstance(melody_ast, ast.Constant)
                and isinstance(melody_ast.value, str)
            ):
                raise ValueError("melody name must be a string literal")
            melody_name = melody_ast.value.lower()
            if melody_name not in _BUZZER_MELODIES:
                raise ValueError(f"unknown melody '{melody_name}'")
            tempo_arg = _extract_call_argument(args_src, keyword="tempo")
            if tempo_arg is None:
                tempo_arg = _extract_call_argument(args_src, position=1)
            tempo_value: Optional[Union[float, int, str]] = None
            if tempo_arg is not None and tempo_arg.strip():
                tempo_value = _resolve_float_arg(tempo_arg, 0.0)
            body.append(
                BuzzerMelody(name=name, melody=melody_name, tempo=tempo_value)
            )
            i += 1
            continue

        m = RE_SERVO_WRITE.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in servo_names:
                angle_arg = _extract_call_argument(args_src, keyword="angle")
                if angle_arg is None:
                    angle_arg = _extract_call_argument(args_src)
                if angle_arg is None or not angle_arg.strip():
                    raise ValueError("Servo.write requires an angle argument")
                angle_expr = _to_c_expr(angle_arg, vars, ctx)
                body.append(ServoWrite(name=name, angle=angle_expr))
                i += 1
                continue

        m = RE_SERVO_WRITE_US.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in servo_names:
                pulse_arg = _extract_call_argument(args_src, keyword="pulse_us")
                if pulse_arg is None:
                    pulse_arg = _extract_call_argument(args_src, keyword="pulse")
                if pulse_arg is None:
                    pulse_arg = _extract_call_argument(args_src)
                if pulse_arg is None or not pulse_arg.strip():
                    raise ValueError("Servo.write_us requires a pulse argument")
                pulse_expr = _to_c_expr(pulse_arg, vars, ctx)
                body.append(ServoWriteMicroseconds(name=name, pulse_us=pulse_expr))
                i += 1
                continue

        m = RE_LCD_WRITE.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                col_arg = _extract_call_argument(args_src, position=0)
                row_arg = _extract_call_argument(args_src, position=1)
                text_arg = _extract_call_argument(args_src, position=2)
                if col_arg is None or row_arg is None or text_arg is None:
                    raise ValueError("LCD.write requires column, row and text arguments")
                clear_arg = _extract_call_argument(args_src, keyword="clear_row")
                align_arg = _extract_call_argument(args_src, keyword="align")
                body.append(
                    LCDWrite(
                        name=name,
                        col=_to_c_expr(col_arg, vars, ctx),
                        row=_to_c_expr(row_arg, vars, ctx),
                        text=_to_c_expr(text_arg, vars, ctx),
                        clear_row=_resolve_bool_arg(clear_arg, True),
                        align=_resolve_align_arg(align_arg),
                    )
                )
                i += 1
                continue

        m = RE_LCD_LINE.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                row_arg = _extract_call_argument(args_src, position=0)
                text_arg = _extract_call_argument(args_src, position=1)
                if row_arg is None or text_arg is None:
                    raise ValueError("LCD.line requires row and text arguments")
                clear_arg = _extract_call_argument(args_src, keyword="clear_row")
                align_arg = _extract_call_argument(args_src, keyword="align")
                body.append(
                    LCDLine(
                        name=name,
                        row=_to_c_expr(row_arg, vars, ctx),
                        text=_to_c_expr(text_arg, vars, ctx),
                        align=_resolve_align_arg(align_arg),
                        clear_row=_resolve_bool_arg(clear_arg, True),
                    )
                )
                i += 1
                continue

        m = RE_LCD_MESSAGE.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                top_arg = _extract_call_argument(args_src, keyword="top")
                if top_arg is None:
                    top_arg = _extract_call_argument(args_src, position=0)
                bottom_arg = _extract_call_argument(args_src, keyword="bottom")
                if bottom_arg is None:
                    bottom_arg = _extract_call_argument(args_src, position=1)
                top_align_arg = _extract_call_argument(args_src, keyword="top_align")
                bottom_align_arg = _extract_call_argument(args_src, keyword="bottom_align")
                clear_rows_arg = _extract_call_argument(args_src, keyword="clear_rows")
                body.append(
                    LCDMessage(
                        name=name,
                        top=None
                        if top_arg is None or not top_arg.strip() or top_arg.strip() == "None"
                        else _to_c_expr(top_arg, vars, ctx),
                        bottom=None
                        if bottom_arg is None or not bottom_arg.strip() or bottom_arg.strip() == "None"
                        else _to_c_expr(bottom_arg, vars, ctx),
                        top_align=_resolve_align_arg(top_align_arg, "left"),
                        bottom_align=_resolve_align_arg(bottom_align_arg, "left"),
                        clear_rows=_resolve_bool_arg(clear_rows_arg, True),
                    )
                )
                i += 1
                continue

        m = RE_LCD_CLEAR.match(line)
        if m:
            name = m.group(1)
            if name in lcd_names:
                body.append(LCDClear(name=name))
                i += 1
                continue

        m = RE_LCD_DISPLAY.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                on_arg = _extract_call_argument(args_src, keyword="on")
                if on_arg is None:
                    on_arg = _extract_call_argument(args_src)
                if on_arg is None or not on_arg.strip():
                    raise ValueError("LCD.display requires a boolean argument")
                body.append(
                    LCDDisplay(name=name, on=_resolve_bool_arg(on_arg, True))
                )
                i += 1
                continue

        m = RE_LCD_BACKLIGHT.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                on_arg = _extract_call_argument(args_src, keyword="on")
                if on_arg is None:
                    on_arg = _extract_call_argument(args_src)
                if on_arg is None or not on_arg.strip():
                    raise ValueError("LCD.backlight requires a boolean argument")
                body.append(
                    LCDBacklight(name=name, on=_resolve_bool_arg(on_arg, True))
                )
                i += 1
                continue

        m = RE_LCD_BRIGHTNESS.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                level_arg = _extract_call_argument(args_src, keyword="level")
                if level_arg is None:
                    level_arg = _extract_call_argument(args_src)
                if level_arg is None or not level_arg.strip():
                    raise ValueError("LCD.brightness requires a level argument")
                body.append(
                    LCDBrightness(name=name, level=_to_c_expr(level_arg, vars, ctx))
                )
                i += 1
                continue

        m = RE_LCD_GLYPH.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                slot_arg = _extract_call_argument(args_src, keyword="slot")
                if slot_arg is None:
                    slot_arg = _extract_call_argument(args_src, position=0)
                bitmap_arg = _extract_call_argument(args_src, keyword="bitmap")
                if bitmap_arg is None:
                    bitmap_arg = _extract_call_argument(args_src, position=1)
                if slot_arg is None or bitmap_arg is None:
                    raise ValueError("LCD.glyph requires slot and bitmap arguments")
                try:
                    bitmap_value = _eval_const(bitmap_arg, vars)
                except Exception as exc:
                    raise ValueError("glyph bitmap must be a list of integers") from exc
                if not isinstance(bitmap_value, (list, tuple)):
                    raise ValueError("glyph bitmap must be a list of integers")
                bitmap_list: List[int] = []
                for entry in bitmap_value:
                    if not isinstance(entry, (int, float)):
                        raise ValueError("glyph bitmap must be a list of integers")
                    bitmap_list.append(int(entry))
                if len(bitmap_list) != 8:
                    raise ValueError("glyph bitmap must contain 8 rows")
                body.append(
                    LCDGlyph(
                        name=name,
                        slot=_to_c_expr(slot_arg, vars, ctx),
                        bitmap=bitmap_list,
                    )
                )
                i += 1
                continue

        m = RE_LCD_PROGRESS.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                row_arg = _extract_call_argument(args_src, position=0)
                value_arg = _extract_call_argument(args_src, position=1)
                if row_arg is None or value_arg is None:
                    raise ValueError("LCD.progress requires row and value arguments")
                max_arg = _extract_call_argument(args_src, keyword="max_value")
                if max_arg is None:
                    max_arg = _extract_call_argument(args_src, position=2)
                width_arg = _extract_call_argument(args_src, keyword="width")
                style_arg = _extract_call_argument(args_src, keyword="style")
                label_arg = _extract_call_argument(args_src, keyword="label")
                if label_arg is None:
                    label_arg = _extract_call_argument(args_src, position=3)
                label_value = None
                if label_arg is not None and label_arg.strip() and label_arg.strip() != "None":
                    label_value = _to_c_expr(label_arg, vars, ctx)
                body.append(
                    LCDProgress(
                        name=name,
                        row=_to_c_expr(row_arg, vars, ctx),
                        value=_to_c_expr(value_arg, vars, ctx),
                        max_value=_resolve_numeric_arg(max_arg, 100),
                        width=_resolve_optional_numeric_arg(width_arg),
                        style=_resolve_style_arg(style_arg, "block"),
                        label=label_value,
                    )
                )
                i += 1
                continue

        m = RE_LCD_ANIMATE.match(line)
        if m:
            name, args_src = m.group(1), m.group(2)
            if name in lcd_names:
                anim_arg = _extract_call_argument(args_src, keyword="style")
                if anim_arg is None:
                    anim_arg = _extract_call_argument(args_src, keyword="animation")
                if anim_arg is None:
                    anim_arg = _extract_call_argument(args_src, position=0)
                row_arg = _extract_call_argument(args_src, keyword="row")
                if row_arg is None:
                    row_arg = _extract_call_argument(args_src, position=1)
                text_arg = _extract_call_argument(args_src, keyword="text")
                if text_arg is None:
                    text_arg = _extract_call_argument(args_src, position=2)
                if anim_arg is None or row_arg is None or text_arg is None:
                    raise ValueError("LCD.animate requires animation name, row and text")
                animation_name = _resolve_animation_arg(anim_arg)
                speed_arg = _extract_call_argument(args_src, keyword="speed_ms")
                if speed_arg is None:
                    speed_arg = _extract_call_argument(args_src, position=3)
                loop_arg = _extract_call_argument(args_src, keyword="loop")
                lcd_tick_names.add(name)
                body.append(
                    LCDAnimate(
                        name=name,
                        animation=animation_name,
                        row=_to_c_expr(row_arg, vars, ctx),
                        text=_to_c_expr(text_arg, vars, ctx),
                        speed_ms=_resolve_numeric_arg(speed_arg, 200),
                        loop=_resolve_bool_arg(loop_arg, False),
                    )
                )
                i += 1
                continue

        m = RE_SERIAL_WRITE.match(line)
        if m:
            owner, arg_src = m.group(1), m.group(2)
            arg_src = arg_src.strip()
            value_expr = ""
            if arg_src:
                value_expr = _to_c_expr(arg_src, vars, ctx)
            else:
                value_expr = '""'
            body.append(SerialWrite(name=owner, value=value_expr, newline=True))
            i += 1
            continue

        # Sleep with expression
        m = RE_SLEEP_EXPR.match(line)
        if m:
            expr = m.group(1)
            try:
                expr_ast = ast.parse(expr, mode="eval").body
            except Exception:
                expr_ast = None
            if expr_ast is not None and not _expr_has_name(expr_ast):
                try:
                    ms = int(_eval_const(expr, vars))
                    body.append(Sleep(ms=ms))
                    i += 1
                    continue
                except Exception:
                    pass
            body.append(Sleep(ms=_to_c_expr(expr, vars, ctx)))
            i += 1
            continue

        # Standalone expressions (evaluate for side effects/consistency)
        try:
            expr_node = ast.parse(line, mode="eval").body
        except SyntaxError:
            expr_node = None
        if expr_node is not None:
            if (
                isinstance(expr_node, ast.Call)
                and isinstance(expr_node.func, ast.Name)
                and expr_node.func.id == "print"
            ):
                i += 1
                continue
            try:
                expr_c = _to_c_expr(line, vars, ctx)
            except Exception:
                expr_c = None
            if expr_c is not None:
                if (
                    isinstance(expr_node, ast.Call)
                    and isinstance(expr_node.func, ast.Attribute)
                    and isinstance(expr_node.func.value, ast.Name)
                    and expr_node.func.attr in {"append", "remove"}
                ):
                    owner_name = expr_node.func.value.id
                    owner_type = var_types.get(owner_name)
                    if owner_type and _is_list_type(owner_type):
                        helpers.add("list")
                        info = list_info.setdefault(owner_name, {})
                        info.setdefault("elem", _list_element_type(owner_type))
                        length = info.get("length")
                        if length is not None:
                            if expr_node.func.attr == "append":
                                info["length"] = length + 1
                            elif length > 0:
                                info["length"] = length - 1
                        current = vars.get(owner_name)
                        arg_value: Optional[object] = None
                        if expr_node.args:
                            arg_node = expr_node.args[0]
                            arg_src = line[arg_node.col_offset : arg_node.end_col_offset]
                            try:
                                arg_value = _eval_const(arg_src, vars)
                            except Exception:
                                arg_value = None
                        if isinstance(current, list):
                            if expr_node.func.attr == "append":
                                current.append(arg_value)
                            else:
                                if arg_value is not None and arg_value in current:
                                    current.remove(arg_value)
                                elif arg_value is None and current:
                                    current.pop(0)
                        else:
                            vars[owner_name] = _ExprStr(owner_name)
                if _expr_has_name(expr_node):
                    body.append(ExprStmt(expr=expr_c))
                else:
                    try:
                        _eval_const(line, vars)
                    except Exception:
                        body.append(ExprStmt(expr=expr_c))
                i += 1
                continue

        # unknown → ignore
        i += 1

    return body


def parse(src: str) -> Program:
    """Parse ``src`` into a :class:`~Reduino.transpile.ast.Program`."""

    lines = src.splitlines()
    setup_body: List[object] = []
    loop_body: List[object]  = []
    ctx: Dict[str, Any] = {
        "target_port": None,
        "vars": {},
        "globals": [],
        "var_types": {},
        "var_declared": set(),
        "helpers": set(),
        "functions": {},
        "function_param_types": {},
        "function_param_orders": {},
        "function_sources": {},
        "function_defs": {},
        "function_signature_aliases": {},
        "function_call_signatures": {},
        "function_primary_signature": {},
        "ultrasonic_measure_calls": set(),
        "ultrasonic_names": set(),
        "ultrasonic_models": {},
        "button_names": set(),
        "button_pins": {},
        "button_callbacks": {},
        "button_poll_names": set(),
        "button_force_loop": False,
        "potentiometer_names": set(),
        "potentiometer_pins": {},
    }
    ctx["vars"]["_helpers"] = ctx["helpers"]

    i = 0
    while i < len(lines):
        raw = lines[i]
        text = raw.strip()

        if not text or text.startswith('#'):
            i += 1; continue

        # early capture at top level as well
        m = RE_TARGET_CALL.match(text)
        if m:
            ctx["target_port"] = m.group(1)
            i += 1; continue

        inline_matches = list(RE_TARGET_INLINE.finditer(text))
        if inline_matches:
            ctx["target_port"] = inline_matches[-1].group(1)
            i += 1; continue

        # ignore imports
        if (
            RE_IMPORT_LED.match(text)
            or RE_IMPORT_SLEEP.match(text)
            or RE_IMPORT_SERIAL.match(text)
            or RE_IMPORT_TARGET.match(text)
            or RE_IMPORT_ULTRASONIC.match(text)
            or RE_IMPORT_BUTTON.match(text)
            or RE_IMPORT_POTENTIOMETER.match(text)
        ):
            i += 1; continue

        # controls
        if _indent_of(raw) == 0 and RE_WHILE_TRUE.match(text):
            block, i = _collect_block(lines, i)
            loop_body.extend(
                _parse_simple_lines(
                    block,
                    ctx,
                    scope="loop",
                    depth=1,
                    loop_depth=1,
                    main_loop=True,
                )
            )
            continue

        if _indent_of(raw) == 0:
            m = RE_WHILE.match(text)
            if m and not RE_WHILE_TRUE.match(text):
                snippet, i = _collect_while_structure(lines, i)
                setup_body.extend(
                    _parse_simple_lines(
                        snippet,
                        ctx,
                        scope="setup",
                        depth=0,
                        loop_depth=0,
                    )
                )
                continue

        if _indent_of(raw) == 0:
            m_def = RE_DEF.match(text)
            if m_def:
                block, i = _collect_block(lines, i)
                _parse_function(m_def.group(1), m_def.group(2), block, ctx)
                continue

            m = RE_FOR_RANGE.match(text)
            if m:
                snippet, i = _collect_for_structure(lines, i)
                setup_body.extend(
                    _parse_simple_lines(
                        snippet,
                        ctx,
                        scope="setup",
                        depth=0,
                        loop_depth=0,
                    )
                )
                continue

        # fallback: simple statement in setup
        if RE_IF.match(text):
            snippet, i = _collect_if_structure(lines, i)
            setup_body.extend(
                _parse_simple_lines(
                    snippet,
                    ctx,
                    scope="setup",
                    depth=0,
                    loop_depth=0,
                )
            )
            continue

        if RE_TRY.match(text):
            snippet, i = _collect_try_structure(lines, i)
            setup_body.extend(
                _parse_simple_lines(
                    snippet,
                    ctx,
                    scope="setup",
                    depth=0,
                    loop_depth=0,
                )
            )
            continue

        setup_body.extend(
            _parse_simple_lines(
                [raw],
                ctx,
                scope="setup",
                depth=0,
                loop_depth=0,
            )
        )
        i += 1

    defs_map: Dict[str, Dict[Tuple[str, ...], FunctionDef]] = ctx.get(
        "function_defs", {}
    )
    call_signatures: Dict[str, List[Tuple[str, ...]]] = ctx.get(
        "function_call_signatures", {}
    )
    primary_signatures: Dict[str, Tuple[str, ...]] = ctx.get(
        "function_primary_signature", {}
    )
    signature_aliases: Dict[str, Dict[Tuple[str, ...], Tuple[str, ...]]] = ctx.get(
        "function_signature_aliases", {}
    )

    selected_functions: List[FunctionDef] = []
    for name, variants in defs_map.items():
        keep: List[Tuple[str, ...]] = []
        used_signatures = call_signatures.get(name, [])
        if used_signatures:
            for sig in used_signatures:
                canonical = signature_aliases.get(name, {}).get(sig, sig)
                if canonical in variants and canonical not in keep:
                    keep.append(canonical)
        else:
            canonical = primary_signatures.get(name)
            if canonical is not None and canonical in variants:
                keep.append(canonical)
            elif variants:
                first_sig = next(iter(variants.keys()))
                keep.append(first_sig)
        for sig in keep:
            selected_functions.append(variants[sig])

    lcd_ticks = [
        LCDTick(name=name)
        for name in sorted(ctx.get("lcd_tick_names", set()))
    ]
    if lcd_ticks:
        loop_body = lcd_ticks + loop_body

    button_polls = [
        ButtonPoll(name=name)
        for name in sorted(ctx.get("button_poll_names", set()))
    ]
    if button_polls:
        loop_body = button_polls + loop_body

    return Program(
        setup_body=setup_body,
        loop_body=loop_body,
        target_port=ctx["target_port"],
        global_decls=ctx.get("globals", []),
        helpers=set(ctx.get("helpers", set())),
        functions=selected_functions,
        ultrasonic_measurements=set(ctx.get("ultrasonic_measure_calls", set())),
    )
RE_LCD_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*LCD\s*\(\s*(.*?)\s*\)\s*$")
RE_LCD_WRITE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.write\(\s*(.*)\s*\)\s*$")
RE_LCD_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.line\(\s*(.*)\s*\)\s*$")
RE_LCD_MESSAGE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.message\(\s*(.*)\s*\)\s*$")
RE_LCD_CLEAR = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.clear\(\s*\)\s*$")
RE_LCD_DISPLAY = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.display\(\s*(.*)\s*\)\s*$")
RE_LCD_BACKLIGHT = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.backlight\(\s*(.*)\s*\)\s*$")
RE_LCD_BRIGHTNESS = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.brightness\(\s*(.*)\s*\)\s*$")
RE_LCD_GLYPH = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.glyph\(\s*(.*)\s*\)\s*$")
RE_LCD_PROGRESS = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.progress\(\s*(.*)\s*\)\s*$")
RE_LCD_ANIMATE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\.animate\(\s*(.*)\s*\)\s*$")
