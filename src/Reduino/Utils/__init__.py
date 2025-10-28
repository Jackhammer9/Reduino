"""Utility helpers for interacting with the Reduino runtime."""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional


class SerialMonitor:
    """High level helper that mirrors Arduino's ``Serial`` interface."""

    def __init__(
        self,
        baud_rate: int = 9600,
        *,
        port: Optional[str] = None,
        newline: str = "\n",
    ) -> None:
        """Initialise a virtual serial monitor configuration.

        Parameters
        ----------
        baud_rate:
            Baud rate that will be passed to ``Serial.begin`` when transpiled.
        port:
            Optional identifier of the serial port used on the host machine.
            The value is stored for diagnostic purposes only.
        newline:
            Delimiter appended to messages written via :meth:`write`. The
            default mirrors :func:`Serial.println` on Arduino boards.
        """

        if baud_rate <= 0:
            raise ValueError("baud_rate must be positive")

        self.baud_rate = int(baud_rate)
        self.port = port
        self.newline = newline
        self._buffer: Deque[str] = deque()

    def write(self, value: object) -> str:
        """Queue ``value`` for emission to the serial monitor.

        The transpiler maps calls to this method to ``Serial.println`` in the
        generated sketch. During host-side execution the helper stores the
        string representation of ``value`` so that :meth:`read` can surface the
        output for inspection.
        """

        text = f"{value}"
        self._buffer.append(text)
        return text

    def read(self) -> str:
        """Return the next buffered message and echo it to stdout."""

        if not self._buffer:
            return ""

        message = self._buffer.popleft()
        print(message + self.newline, end="")
        return message
