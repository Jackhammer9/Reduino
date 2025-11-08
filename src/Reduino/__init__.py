from __future__ import annotations

"""User-facing helpers for the Reduino transpiler package."""

__all__ = ["target"]
__version__ = "1.1.0"

import pathlib
import sys
import tempfile
from typing import List, Type

from Reduino.toolchain.pio import compile_upload, ensure_pio, write_project
from Reduino.transpile.ast import LCDDecl, Program, ServoDecl
from Reduino.transpile.emitter import emit
from Reduino.transpile.parser import parse


def _program_contains(program: Program, node_type: Type[object]) -> bool:
    """Recursively determine whether ``program`` includes ``node_type``."""

    seen: set[int] = set()

    def _visit(value: object) -> bool:
        if isinstance(value, node_type):
            return True
        if isinstance(value, (str, bytes, bytearray)):
            return False
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if _visit(item):
                    return True
            return False
        if isinstance(value, dict):
            for item in value.values():
                if _visit(item):
                    return True
            return False
        if hasattr(value, "__dict__"):
            key = id(value)
            if key in seen:
                return False
            seen.add(key)
            for attr_value in value.__dict__.values():
                if _visit(attr_value):
                    return True
        return False

    return _visit(program)


def _collect_required_libraries(program: Program) -> List[str]:
    """Return PlatformIO libraries required by the transpiled program."""

    requirements: List[str] = []
    if _program_contains(program, ServoDecl):
        requirements.append("Servo")
    lcd_interfaces: set[str] = set()

    def _visit(value: object) -> None:
        if isinstance(value, LCDDecl):
            lcd_interfaces.add(value.interface)
            return
        if isinstance(value, (str, bytes, bytearray)):
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _visit(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                _visit(item)
            return
        if hasattr(value, "__dict__"):
            for attr_value in value.__dict__.values():
                _visit(attr_value)

    _visit(program)
    if "parallel" in lcd_interfaces:
        requirements.append("LiquidCrystal")
    if "i2c" in lcd_interfaces:
        requirements.append("LiquidCrystal_I2C")
    return requirements


def target(port: str, *, upload: bool = True) -> None:
    """Transpile the invoking script and prepare a PlatformIO project.

    Parameters
    ----------
    port:
        Serial port that the generated project should target.
    upload:
        When set to ``True`` the helper also triggers ``pio run -t upload``
        after generating the temporary project directory.  Uploading is
        disabled by default so that unit tests can exercise the helper without
        requiring an Arduino board to be connected.
    """

    ensure_pio()

    main_file = pathlib.Path(sys.modules["__main__"].__file__)
    src = main_file.read_text(encoding="utf-8")
    program = parse(src)
    required_libs = _collect_required_libraries(program)
    if "Servo" in required_libs:
        print(
            "Reduino: Servo support requires the PlatformIO Servo library. "
            "PlatformIO will download it automatically if it's missing.",
            file=sys.stderr,
        )
    cpp = emit(program)

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="reduino-pio-"))
    write_project(tmp, cpp, port=port, lib_deps=required_libs)
    if upload:
        compile_upload(tmp)

    return cpp