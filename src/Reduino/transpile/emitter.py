"""Translate Reduino AST nodes into Arduino-flavoured C++ code."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

from .ast import (
    BreakStmt,
    FunctionDef,
    ExprStmt,
    ForRangeLoop,
    IfStatement,
    LedDecl,
    LedOff,
    LedOn,
    LedToggle,
    Program,
    ReturnStmt,
    Sleep,
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
    indent: str = "  ",
    *,
    in_setup: bool = False,
    emitted_pin_modes: Optional[Set[Tuple[str, str]]] = None,
) -> List[str]:
    """Emit a block of statements as C++ source lines."""
    lines: List[str] = []
    for node in nodes:
        # Structured control we support
        if type(node).__name__ == "Repeat":
            # Repeat(count=int, body=list)
            count = getattr(node, "count", 0)
            body = getattr(node, "body", [])
            lines.append(f"{indent}for (int __i = 0; __i < {count}; ++__i) {{")
            lines.extend(
                _emit_block(
                    body,
                    led_pin,
                    led_state,
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
                )
            )
            lines.append(f"{indent}}}")
            continue

        if isinstance(node, IfStatement):
            for idx, branch in enumerate(node.branches):
                keyword = "if" if idx == 0 else "else if"
                cond = branch.condition
                lines.append(f"{indent}{keyword} ({cond}) {{")
                lines.extend(
                    _emit_block(
                        branch.body,
                        led_pin,
                        led_state,
                        indent + "  ",
                        in_setup=in_setup,
                        emitted_pin_modes=emitted_pin_modes,
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
                        indent + "  ",
                        in_setup=in_setup,
                        emitted_pin_modes=emitted_pin_modes,
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
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
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
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
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
                    indent + "  ",
                    in_setup=in_setup,
                    emitted_pin_modes=emitted_pin_modes,
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
                        indent + "  ",
                        in_setup=in_setup,
                        emitted_pin_modes=emitted_pin_modes,
                    )
                )
                lines.append(f"{indent}}}")
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

        if isinstance(node, LedDecl):
            # Record pin and create state symbol.
            led_pin[node.name] = node.pin  # pin may be int or C-expr string
            var = f"__state_{node.name}"
            led_state[node.name] = var
            if in_setup:
                if emitted_pin_modes is None:
                    emitted_pin_modes = set()
                pin_expr = _emit_expr(node.pin)
                key = (node.name, pin_expr)
                if key not in emitted_pin_modes:
                    emitted_pin_modes.add(key)
                    lines.append(f"{indent}pinMode({pin_expr}, OUTPUT);")
            continue

        elif isinstance(node, LedOn):
            pin = led_pin.get(node.name, 13)
            pin_code = _emit_expr(pin)
            var = led_state.get(node.name, f"__state_{node.name}")
            lines.append(f"{indent}{var} = true;")
            lines.append(f"{indent}digitalWrite({pin_code}, HIGH);")

        elif isinstance(node, LedOff):
            pin = led_pin.get(node.name, 13)
            pin_code = _emit_expr(pin)
            var = led_state.get(node.name, f"__state_{node.name}")
            lines.append(f"{indent}{var} = false;")
            lines.append(f"{indent}digitalWrite({pin_code}, LOW);")

        elif isinstance(node, LedToggle):
            pin = led_pin.get(node.name, 13)
            pin_code = _emit_expr(pin)
            var = led_state.get(node.name, f"__state_{node.name}")
            lines.append(f"{indent}{var} = !{var};")
            lines.append(
                f"{indent}digitalWrite({pin_code}, {var} ? HIGH : LOW);"
            )

        elif isinstance(node, Sleep):
            lines.append(f"{indent}delay({_emit_expr(node.ms)});")

        # Unknown nodes are ignored for now
    return lines

def emit(ast: Program) -> str:
    """Serialize a :class:`~Reduino.transpile.ast.Program` into Arduino C++."""

    led_pin: Dict[str, Union[int, str]] = {}
    led_state: Dict[str, str] = {}
    helpers = getattr(ast, "helpers", set())

    globals_: List[str] = []
    setup_lines: List[str] = []
    loop_lines: List[str] = []

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
            var = f"__state_{node.name}"
            led_state[node.name] = var
            line = f"bool {var} = false;"
            if line not in globals_:
                globals_.append(line)
            led_pin[node.name] = node.pin

    for node in (loop_body or []):
        if isinstance(node, LedDecl):
            var = f"__state_{node.name}"
            if node.name not in led_state:
                led_state[node.name] = var
                line = f"bool {var} = false;"
                if line not in globals_:
                    globals_.append(line)
            if node.name not in led_pin:
                led_pin[node.name] = node.pin
            # Ensure pinMode exists in setup for pins declared in loop
            setup_lines.append(f"  pinMode({_emit_expr(node.pin)}, OUTPUT);")

    # Pass 2: emit statements
    setup_lines.extend(
        _emit_block(
            setup_body or [],
            led_pin,
            led_state,
            in_setup=True,
            emitted_pin_modes=pin_mode_emitted,
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
                    in_setup=False,
                    emitted_pin_modes=pin_mode_emitted,
                )
            )

    # Normal loop body (preferred path)
    loop_lines.extend(
        _emit_block(
            loop_body or [],
            led_pin,
            led_state,
            in_setup=False,
            emitted_pin_modes=pin_mode_emitted,
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
            indent="  ",
            in_setup=False,
            emitted_pin_modes=set(),
        )
        function_sections.append(header)
        if body_lines:
            function_sections.append("\n".join(body_lines))
            function_sections.append("\n")
        function_sections.append("}\n\n")

    # Stitch sections
    parts: List[str] = [HEADER]
    if "len" in helpers:
        parts.append(LEN_HELPER_SNIPPET + "\n")
    if globals_:
        parts.append("\n".join(globals_) + "\n\n")
    if function_sections:
        parts.append("".join(function_sections))

    parts.append(SETUP_START)
    parts.append("\n".join(setup_lines) if setup_lines else "  // no setup actions")
    parts.append("\n" + SETUP_END)

    parts.append(LOOP_START)
    parts.append("\n".join(loop_lines) if loop_lines else "  // no loop actions")
    parts.append("\n" + LOOP_END)

    return "".join(parts)
