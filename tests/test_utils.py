import pytest

from Reduino.Utils import SerialMonitor


def test_serial_monitor_buffers_and_reads(capfd):
    monitor = SerialMonitor(baud_rate=9600)
    monitor.write("hello")
    monitor.write("world")

    first = monitor.read()
    out = capfd.readouterr().out
    assert first == "hello"
    assert "hello\n" in out

    second = monitor.read()
    out = capfd.readouterr().out
    assert second == "world"
    assert "world\n" in out

    assert monitor.read() == ""


def test_serial_monitor_requires_positive_baud():
    with pytest.raises(ValueError):
        SerialMonitor(0)
