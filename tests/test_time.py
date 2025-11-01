"""Tests for the :mod:`Reduino.Utils` utilities."""

from __future__ import annotations

import pytest

from Reduino.Utils import sleep


def test_sleep_converts_to_seconds():
    calls: list[float] = []
    sleep(250, sleep_func=calls.append)
    assert pytest.approx(calls) == [0.25]


def test_sleep_validates_duration():
    with pytest.raises(ValueError):
        sleep(-1)


def test_sleep_uses_injected_callable():
    calls: list[float] = []

    def fake_sleep(value: float) -> None:
        calls.append(value)

    sleep(500, sleep_func=fake_sleep)

    assert calls == [0.5]


def test_sleep_accepts_float_duration():
    calls: list[float] = []
    sleep(12.5, sleep_func=calls.append)
    assert calls == [0.0125]
