from __future__ import annotations

import pathlib

from Reduino import _collect_required_libraries
from Reduino.toolchain.pio import write_project
from Reduino.transpile.ast import Program, ServoDecl


def _read_ini(tmp_path: pathlib.Path) -> str:
    return (tmp_path / "platformio.ini").read_text(encoding="utf-8")


def test_write_project_includes_lib_deps(tmp_path) -> None:
    write_project(
        tmp_path,
        cpp_code="void setup() {}\nvoid loop() {}\n",
        port="/dev/ttyACM0",
        lib_deps=["Servo"],
    )
    ini = _read_ini(tmp_path)
    assert "lib_deps =" in ini
    assert "  Servo" in ini


def test_write_project_omits_empty_lib_deps(tmp_path) -> None:
    write_project(
        tmp_path,
        cpp_code="void setup() {}\nvoid loop() {}\n",
        port="/dev/ttyACM0",
    )
    ini = _read_ini(tmp_path)
    assert "lib_deps" not in ini


def test_collect_required_libraries_detects_servo() -> None:
    program = Program(setup_body=[ServoDecl(name="servo", pin=9)])
    assert _collect_required_libraries(program) == ["Servo"]


def test_collect_required_libraries_handles_absence() -> None:
    program = Program()
    assert _collect_required_libraries(program) == []
