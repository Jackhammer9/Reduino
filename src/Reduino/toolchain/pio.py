from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List

PIO_INI = """[env:uno]
platform = atmelavr
board = uno
framework = arduino
upload_port = {port}

{lib_section}
"""


def _format_lib_section(libraries: Iterable[str] | None) -> str:
    """Render a ``lib_deps`` section for ``platformio.ini`` if needed."""

    if not libraries:
        return ""

    unique: List[str] = []
    for entry in libraries:
        if not entry:
            continue
        if entry not in unique:
            unique.append(entry)

    if not unique:
        return ""

    lines = ["lib_deps ="]
    lines.extend(f"  {name}" for name in unique)
    return "\n".join(lines)

def ensure_pio() -> None:
    try:
        subprocess.run(["pio", "--version"], check=True, stdout=subprocess.DEVNULL)
    except Exception as e:
        raise RuntimeError(
            "PlatformIO (pio) not found. Install with: pip install platformio"
        ) from e

def write_project(
    project_dir: Path,
    cpp_code: str,
    port: str,
    *,
    lib_deps: Iterable[str] | None = None,
) -> None:
    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "main.cpp").write_text(cpp_code, encoding="utf-8")
    lib_section = _format_lib_section(lib_deps)
    ini_contents = PIO_INI.format(port=port, lib_section=lib_section).rstrip() + "\n"
    (project_dir / "platformio.ini").write_text(ini_contents, encoding="utf-8")

def compile_upload(project_dir: str | Path) -> None:
    project_dir = Path(project_dir)
    # First run triggers toolchain download automatically
    subprocess.run(["pio", "run"], cwd=project_dir, check=True)
    subprocess.run(["pio", "run", "-t", "upload"], cwd=project_dir, check=True)
