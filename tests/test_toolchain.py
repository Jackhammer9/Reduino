from __future__ import annotations

import pathlib

import pytest

from Reduino import _collect_required_libraries

from Reduino.toolchain.pio import validate_platform_board, write_project
from Reduino.transpile.ast import LCDDecl, Program, ServoDecl


def _read_ini(tmp_path: pathlib.Path) -> str:
    return (tmp_path / "platformio.ini").read_text(encoding="utf-8")


def test_write_project_includes_lib_deps(tmp_path) -> None:
    write_project(
        tmp_path,
        cpp_code="void setup() {}\nvoid loop() {}\n",
        port="/dev/ttyACM0",
        platform="atmelavr",
        board="uno",
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
        platform="atmelavr",
        board="uno",
    )
    ini = _read_ini(tmp_path)
    assert "lib_deps" not in ini


def test_write_project_renders_platform_and_board(tmp_path) -> None:
    write_project(
        tmp_path,
        cpp_code="void setup() {}\nvoid loop() {}\n",
        port="/dev/ttyUSB0",
        platform="atmelmegaavr",
        board="nano_every",
    )
    ini = _read_ini(tmp_path)
    assert "[env:nano_every]" in ini
    assert "platform = atmelmegaavr" in ini
    assert "board = nano_every" in ini


def test_validate_platform_board_rejects_unknown_platform() -> None:
    with pytest.raises(ValueError):
        validate_platform_board("mystery", "uno")


def test_validate_platform_board_rejects_unknown_board() -> None:
    with pytest.raises(ValueError):
        validate_platform_board("atmelavr", "not-a-board")


def test_validate_platform_board_rejects_mismatched_pair() -> None:
    with pytest.raises(ValueError):
        validate_platform_board("atmelavr", "nano_every")


def test_collect_required_libraries_detects_servo() -> None:
    program = Program(setup_body=[ServoDecl(name="servo", pin=9)])
    assert _collect_required_libraries(program) == ["Servo"]


def test_collect_required_libraries_handles_absence() -> None:
    program = Program()
    assert _collect_required_libraries(program) == []


def test_collect_required_libraries_detects_parallel_lcd() -> None:
    program = Program(
        setup_body=[
            LCDDecl(
                name="lcd",
                cols=16,
                rows=2,
                interface="parallel",
                rs=12,
                en=11,
                d4=5,
                d5=4,
                d6=3,
                d7=2,
            )
        ]
    )

    assert _collect_required_libraries(program) == ["LiquidCrystal"]


def test_collect_required_libraries_detects_i2c_lcd() -> None:
    program = Program(
        setup_body=[
            LCDDecl(
                name="panel",
                cols=20,
                rows=4,
                interface="i2c",
                i2c_addr="0x27",
            )
        ]
    )

    assert _collect_required_libraries(program) == ["LiquidCrystal_I2C"]
