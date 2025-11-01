"""Communication helpers mirroring Arduino runtime interfaces."""

try:  # pragma: no cover - exercised in real environments
    import serial  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - exercised in real environments
    serial = None  # type: ignore[assignment]

from .SerialMonitor import SerialMonitor

__all__ = ["SerialMonitor", "serial"]
