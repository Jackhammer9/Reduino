from types import SimpleNamespace

import pytest

from Reduino.Utils import SerialMonitor


def test_serial_monitor_reads_from_serial_port(monkeypatch, capfd):
    lines = [b"hello world\r\n", b"", b"ignored"]
    writes = []

    class FakeSerial:
        def __init__(self, *, port: str, baudrate: int, timeout: float):
            self.port = port
            self.baudrate = baudrate
            self.timeout = timeout
            self.is_open = True

        def write(self, payload: bytes) -> int:
            writes.append(payload)
            return len(payload)

        def readline(self) -> bytes:
            return lines.pop(0) if lines else b""

        def close(self) -> None:
            self.is_open = False

    fake_serial = SimpleNamespace(Serial=FakeSerial)
    monkeypatch.setattr("Reduino.Utils.serial", fake_serial)

    monitor = SerialMonitor(baud_rate=115200, port="/dev/ttyUSB0", timeout=0.5)
    assert monitor.baud_rate == 115200
    assert monitor.port == "/dev/ttyUSB0"

    monitor.write("ping")
    assert writes == [b"ping\n"]

    message = monitor.read()
    assert message == "hello world"
    assert capfd.readouterr().out == "hello world\n"

    assert monitor.read() == ""
    assert capfd.readouterr().out == ""

    assert monitor.read(emit="mcu") == ""
    assert capfd.readouterr().out == ""

    assert monitor.read("host") == "ignored"
    assert capfd.readouterr().out == "ignored\n"


def test_serial_monitor_requires_positive_baud():
    with pytest.raises(ValueError):
        SerialMonitor(0)


def test_serial_monitor_requires_connection_before_read(monkeypatch):
    monkeypatch.setattr("Reduino.Utils.serial", None)
    monitor = SerialMonitor()

    with pytest.raises(RuntimeError, match="No serial port configured"):
        monitor.read()


def test_serial_monitor_rejects_invalid_emit(monkeypatch):
    fake_serial = SimpleNamespace(Serial=object)
    monkeypatch.setattr("Reduino.Utils.serial", fake_serial)
    monitor = SerialMonitor()

    with pytest.raises(ValueError, match="emit must be 'host', 'mcu', or 'both'"):
        monitor.read("invalid")
