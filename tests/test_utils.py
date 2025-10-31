"""Tests for :mod:`Reduino.Utils` helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from Reduino.Utils import SerialMonitor


class DummySerial:
    """In-memory serial implementation used for testing."""

    def __init__(self, *, port: str, baudrate: int, timeout: float) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self._writes: List[bytes] = []
        self._reads: List[bytes] = []

    def prime_reads(self, *payloads: bytes) -> None:
        self._reads.extend(payloads)

    def write(self, payload: bytes) -> int:  # pragma: no cover - exercised via SerialMonitor.write
        self._writes.append(payload)
        return len(payload)

    def readline(self) -> bytes:  # pragma: no cover - exercised via SerialMonitor.read
        return self._reads.pop(0) if self._reads else b""

    def close(self) -> None:  # pragma: no cover - exercised via SerialMonitor.close
        self.is_open = False


def _patch_serial(monkeypatch: pytest.MonkeyPatch, serial_obj: Any) -> None:
    monkeypatch.setattr("Reduino.Utils.serial", serial_obj)


def test_serial_monitor_connects_and_reads(monkeypatch: pytest.MonkeyPatch, capfd) -> None:
    dummy = DummySerial(port="/dev/ttyUSB0", baudrate=115200, timeout=0.5)
    dummy.prime_reads(b"hello\r\n", b"world\n", b"")
    fake_serial = SimpleNamespace(Serial=lambda **kwargs: dummy)
    _patch_serial(monkeypatch, fake_serial)

    monitor = SerialMonitor(baud_rate=115200, port="/dev/ttyUSB0", timeout=0.5)
    assert monitor.baud_rate == 115200
    assert monitor.port == "/dev/ttyUSB0"

    assert monitor.write("ping") == "ping"
    assert dummy._writes == [b"ping\n"]

    first = monitor.read()
    assert first == "hello"
    assert capfd.readouterr().out == "hello\n"

    second = monitor.read("host")
    assert second == "world"
    assert capfd.readouterr().out == "world\n"

    third = monitor.read("mcu")
    assert third == ""
    assert capfd.readouterr().out == ""

    monitor.close()
    assert dummy.is_open is False


def test_serial_monitor_requires_positive_baud() -> None:
    with pytest.raises(ValueError):
        SerialMonitor(0)


def test_serial_monitor_requires_connection_before_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_serial(monkeypatch, None)
    monitor = SerialMonitor()
    with pytest.raises(RuntimeError, match="No serial port configured"):
        monitor.read()


def test_serial_monitor_rejects_invalid_emit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_serial(monkeypatch, SimpleNamespace(Serial=DummySerial))
    monitor = SerialMonitor()
    with pytest.raises(ValueError, match="emit must be 'host', 'mcu', or 'both'"):
        monitor.read("invalid")


def test_serial_monitor_raises_when_pyserial_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_serial(monkeypatch, None)
    monitor = SerialMonitor()
    with pytest.raises(RuntimeError, match="pyserial is required"):
        monitor.connect("/dev/ttyUSB0")
