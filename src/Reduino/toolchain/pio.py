from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable, List

SUPPORTED_PLATFORMS: dict[str, set[str]] = {
    "atmelavr": {"uno", "nano"},
    "atmelsam": {"due"},
    "espressif32": {"esp32dev", "esp32doit-devkit-v1"},
}

BOARD_TO_PLATFORM = {
    board: platform
    for platform, boards in SUPPORTED_PLATFORMS.items()
    for board in boards
}


PIO_INI = """[env:{env_name}]
platform = {platform}
board = {board}
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


def _sanitize_env_name(board: str) -> str:
    """Return a safe PlatformIO environment name based on ``board``."""

    return re.sub(r"[^A-Za-z0-9_]+", "_", board)


def validate_platform_board(platform: str, board: str) -> None:
    """Ensure the requested PlatformIO ``platform``/``board`` pair is supported."""

    if platform not in SUPPORTED_PLATFORMS:
        supported = ", ".join(sorted(SUPPORTED_PLATFORMS))
        raise ValueError(
            f"Unsupported PlatformIO platform '{platform}'. Supported platforms: {supported}."
        )

    if board not in BOARD_TO_PLATFORM:
        supported = ", ".join(sorted(BOARD_TO_PLATFORM))
        raise ValueError(
            f"Unsupported PlatformIO board '{board}'. Supported boards: {supported}."
        )

    required_platform = BOARD_TO_PLATFORM[board]
    if required_platform != platform:
        raise ValueError(
            f"Board '{board}' requires PlatformIO platform '{required_platform}', not '{platform}'."
        )


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
    platform: str = "atmelavr",
    board: str = "uno",
    lib_deps: Iterable[str] | None = None,
) -> None:
    validate_platform_board(platform, board)
    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "main.cpp").write_text(cpp_code, encoding="utf-8")
    lib_section = _format_lib_section(lib_deps)
    env_name = _sanitize_env_name(board)
    ini_contents = (
        PIO_INI.format(
            env_name=env_name,
            platform=platform,
            board=board,
            port=port,
            lib_section=lib_section,
        ).rstrip()
        + "\n"
    )
    (project_dir / "platformio.ini").write_text(ini_contents, encoding="utf-8")

def compile_upload(project_dir: str | Path) -> None:
    project_dir = Path(project_dir)
    # First run triggers toolchain download automatically
    subprocess.run(["pio", "run"], cwd=project_dir, check=True)
    subprocess.run(["pio", "run", "-t", "upload"], cwd=project_dir, check=True)
