from __future__ import annotations

"""User-facing helpers for the Reduino transpiler package."""

__all__ = ["target"]
__version__ = "0.0.3"

import pathlib
import sys
import tempfile

from Reduino.toolchain.pio import compile_upload, ensure_pio, write_project
from Reduino.transpile.emitter import emit
from Reduino.transpile.parser import parse


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
    cpp = emit(parse(src))

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="reduino-pio-"))
    write_project(tmp, cpp, port=port)
    if upload:
        compile_upload(tmp)

    return cpp