"""Utility helpers for interacting with the Reduino runtime."""

from __future__ import annotations

from typing import Optional

try:
    import serial  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - exercised in real environments
    serial = None  # type: ignore[assignment]


class SerialMonitor:
    """High level helper that mirrors Arduino's ``Serial`` interface."""

    def __init__(
        self,
        baud_rate: int = 9600,
        port: Optional[str] = None,
        timeout: float = 1.0,
        newline: str = "\n",
    ) -> None:
        """Initialise a serial monitor configuration bound to an MCU port.

        Parameters
        ----------
        baud_rate:
            Baud rate that will be passed to ``Serial.begin`` when transpiled
            and used when establishing a host serial connection.
        port:
            Optional identifier of the serial port used on the host machine.
            If supplied the monitor immediately connects to it.
        timeout:
            Read timeout (in seconds) applied to the host serial connection.
        newline:
            Delimiter appended to messages written via :meth:`write`. The
            default mirrors :func:`Serial.println` on Arduino boards.
        """

        if baud_rate <= 0:
            raise ValueError("baud_rate must be positive")

        self.baud_rate = int(baud_rate)
        self.port = port
        self.timeout = timeout
        self.newline = newline
        self._serial: Optional["serial.Serial"] = None

        if port is not None:
            self.connect(port)

    def connect(self, port: str) -> None:
        """Open a serial connection to ``port`` using the configured baud rate."""

        if serial is None:
            raise RuntimeError(
                "pyserial is required for host-side SerialMonitor reads; install the "
                "'pyserial' package to enable this functionality."
            )

        if self._serial is not None and self._serial.is_open:  # pragma: no cover - safety net
            self._serial.close()

        self.port = port
        self._serial = serial.Serial(port=port, baudrate=self.baud_rate, timeout=self.timeout)

    def close(self) -> None:
        """Terminate the current serial connection if one exists."""

        if self._serial is not None and self._serial.is_open:
            self._serial.close()

        self._serial = None

    def write(self, value: object) -> str:
        """Send ``value`` to the connected MCU via the serial monitor."""

        text = f"{value}"
        if self._serial is not None and self._serial.is_open:
            payload = (text + self.newline).encode("utf-8")
            self._serial.write(payload)
        return text

    def read(self, emit: str = "both") -> str:
        """Read the next message from the MCU and optionally echo it to stdout."""

        if emit not in {"host", "mcu", "both"}:
            raise ValueError("emit must be 'host', 'mcu', or 'both'")

        host_enabled = emit in {"host", "both"}
        if not host_enabled:
            return ""

        if self._serial is None:
            raise RuntimeError("No serial port configured. Call connect() with a valid port first.")

        raw = self._serial.readline()
        if not raw:
            return ""

        message = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if message:
            print(message + self.newline, end="")
        return message


def map(value: float, from_low: float, from_high: float, to_low: float, to_high: float) -> float:
    """Linearly map ``value`` from one range to another."""

    if from_low == from_high:
        raise ValueError("from_low and from_high must be different")

    ratio = (value - from_low) / (from_high - from_low)
    return to_low + ratio * (to_high - to_low)
