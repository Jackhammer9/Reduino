from __future__ import annotations
import subprocess, sys, os
from pathlib import Path

PIO_INI = """[env:uno]
platform = atmelavr
board = uno
framework = arduino
upload_port = {port}
"""

def ensure_pio() -> None:
    try:
        subprocess.run(["pio", "--version"], check=True, stdout=subprocess.DEVNULL)
    except Exception as e:
        raise RuntimeError(
            "PlatformIO (pio) not found. Install with: pip install platformio"
        ) from e

def write_project(project_dir: Path, cpp_code: str, port: str) -> None:
    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "main.cpp").write_text(cpp_code, encoding="utf-8")
    (project_dir / "platformio.ini").write_text(PIO_INI.format(port=port), encoding="utf-8")

def compile_upload(project_dir: str | Path) -> None:
    project_dir = Path(project_dir)
    # First run triggers toolchain download automatically
    subprocess.run(["pio", "run"], cwd=project_dir, check=True)
    subprocess.run(["pio", "run", "-t", "upload"], cwd=project_dir, check=True)
