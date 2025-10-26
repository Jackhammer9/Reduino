"""Tests for the :mod:`Reduino.Time` utilities."""

from __future__ import annotations

import pytest

from Reduino.Time import Sleep


def test_sleep_converts_to_seconds():
    sleep = Sleep(250)
    assert pytest.approx(sleep.seconds) == 0.25


def test_sleep_validates_duration():
    with pytest.raises(ValueError):
        Sleep(-1)


def test_sleep_wait_uses_injected_callable():
    calls: list[float] = []

    def fake_sleep(value: float) -> None:
        calls.append(value)

    sleeper = Sleep(500, sleep_func=fake_sleep)
    sleeper.wait()

    assert calls == [0.5]


def test_sleep_is_callable():
    calls: list[float] = []

    sleeper = Sleep(1000, sleep_func=calls.append)
    sleeper()

    assert calls == [1.0]
