"""Behavioural tests for the high-level actuator helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Callable

import pytest

from Reduino.Actuators import Led, RGBLed


def _patch_sleep(monkeypatch: pytest.MonkeyPatch, collector: list[float]) -> None:
    """Patch the module-level ``Sleep`` helper to record delays."""

    def fake_sleep(duration: float, *, sleep_func: Callable | None = None) -> None:  # pragma: no cover - helper
        collector.append(duration)

    monkeypatch.setattr("Reduino.Actuators.Sleep", fake_sleep)


class TestLed:
    """Tests covering the :class:`Reduino.Actuators.Led` helper."""

    def test_defaults_and_pin_override(self) -> None:
        led_default = Led()
        assert led_default.pin == 13
        assert led_default.get_state() is False
        assert led_default.get_brightness() == 0

        led_custom = Led(pin=7)
        assert led_custom.pin == 7
        assert led_custom.get_state() is False

    @pytest.mark.parametrize("value", [0, 1, 255])
    def test_set_brightness_within_bounds(self, value: int) -> None:
        led = Led()
        led.set_brightness(value)
        assert led.get_brightness() == value
        assert led.get_state() is (value > 0)

    @pytest.mark.parametrize("value", [-1, 256])
    def test_set_brightness_rejects_out_of_bounds(self, value: int) -> None:
        led = Led()
        with pytest.raises(ValueError, match="brightness must be between 0 and 255"):
            led.set_brightness(value)

    def test_toggle_transitions_and_helpers(self) -> None:
        led = Led()
        led.on()
        assert led.get_state() is True
        assert led.get_brightness() == 255

        led.toggle()
        assert led.get_state() is False
        assert led.get_brightness() == 0

        led.toggle()
        assert led.get_state() is True

    def test_blink_uses_sleep_and_restores_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        led = Led()
        led.set_brightness(128)
        calls: list[float] = []
        _patch_sleep(monkeypatch, calls)

        led.blink(duration_ms=50, times=2)

        assert led.get_state() is False
        assert led.get_brightness() == 0
        assert calls == [50, 50, 50, 50]

    @pytest.mark.parametrize(
        "duration,times,expected",
        [(-1, 1, "duration_ms must be non-negative"), (10, 0, "times must be positive")],
    )
    def test_blink_validates_arguments(
        self, duration: int, times: int, expected: str
    ) -> None:
        led = Led()
        with pytest.raises(ValueError, match=expected):
            led.blink(duration_ms=duration, times=times)

    def test_fade_in_and_out_respect_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        led = Led()
        led.set_brightness(10)
        calls: list[float] = []
        _patch_sleep(monkeypatch, calls)

        led.fade_in(step=120, delay_ms=5)
        assert led.get_brightness() == 255
        assert led.get_state() is True

        led.fade_out(step=200, delay_ms=5)
        assert led.get_brightness() == 0
        assert led.get_state() is False

        assert all(call == 5 for call in calls)

    @pytest.mark.parametrize(
        "method,kwargs,message",
        [
            ("fade_in", {"step": 0}, "step must be positive"),
            ("fade_out", {"step": 0}, "step must be positive"),
            ("fade_in", {"delay_ms": -1}, "delay_ms must be non-negative"),
            ("fade_out", {"delay_ms": -1}, "delay_ms must be non-negative"),
        ],
    )
    def test_fade_validates_arguments(self, method: str, kwargs: dict, message: str) -> None:
        led = Led()
        func = getattr(led, method)
        with pytest.raises(ValueError, match=message):
            func(**kwargs)

    @pytest.mark.parametrize(
        "pattern,expected_final,expected_calls",
        [
            ([1, 0, 128, 0], 0, [25, 25, 25]),
            ([255, 128], 128, [10]),
        ],
    )
    def test_flash_pattern_accepts_binary_and_pwm_entries(
        self,
        pattern: Sequence[int],
        expected_final: int,
        expected_calls: list[int],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        led = Led()
        calls: list[float] = []
        _patch_sleep(monkeypatch, calls)

        led.flash_pattern(pattern, delay_ms=expected_calls[0] if expected_calls else 0)
        assert led.get_brightness() == expected_final
        assert calls == expected_calls

    def test_flash_pattern_validates_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        led = Led()
        _patch_sleep(monkeypatch, [])

        with pytest.raises(ValueError, match="pattern values must be"):
            led.flash_pattern([300])

    def test_flash_pattern_accepts_empty_sequence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        led = Led()
        calls: list[float] = []
        _patch_sleep(monkeypatch, calls)

        led.flash_pattern([], delay_ms=15)

        assert calls == []
        assert led.get_state() is False
        assert led.get_brightness() == 0


class TestRGBLed:
    """Tests covering the :class:`Reduino.Actuators.RGBLed` helper."""

    def test_pin_validation_and_defaults(self) -> None:
        led = RGBLed(9, 10, 11)
        assert led.pins == (9, 10, 11)
        assert led.get_color() == (0, 0, 0)
        assert led.get_state() is False

        with pytest.raises(TypeError):
            RGBLed("9", 10, 11)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            RGBLed(-1, 10, 11)

    def test_color_management_and_state_updates(self) -> None:
        led = RGBLed(3, 5, 6)

        led.set_color(10, 20, 30)
        assert led.get_color() == (10, 20, 30)
        assert led.get_state() is True

        led.off()
        assert led.get_color() == (0, 0, 0)
        assert led.get_state() is False

        led.on(1, 2, 3)
        assert led.get_color() == (1, 2, 3)

        with pytest.raises(ValueError):
            led.set_color(256, 0, 0)
        with pytest.raises(TypeError):
            led.set_color(1, 2, 3.5)  # type: ignore[arg-type]

    def test_fade_interpolates_steps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        led = RGBLed(4, 5, 6)
        led.set_color(0, 0, 0)
        calls: list[float] = []
        _patch_sleep(monkeypatch, calls)

        led.fade(10, 20, 30, duration_ms=30, steps=3)
        assert led.get_color() == (10, 20, 30)
        assert calls == [10.0, 10.0]

        led.fade(10, 20, 30, duration_ms=0, steps=3)
        assert calls == [10.0, 10.0]

        with pytest.raises(ValueError):
            led.fade(0, 0, 0, duration_ms=-1)
        with pytest.raises(ValueError):
            led.fade(0, 0, 0, steps=0)

    def test_blink_restores_original_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        led = RGBLed(7, 8, 9)
        led.set_color(5, 15, 25)
        calls: list[float] = []
        _patch_sleep(monkeypatch, calls)

        led.blink(255, 0, 0, times=2, delay_ms=12)
        assert led.get_color() == (5, 15, 25)
        assert calls == [12, 12, 12, 12]

        with pytest.raises(ValueError):
            led.blink(0, 0, 0, times=0)
        with pytest.raises(ValueError):
            led.blink(0, 0, 0, delay_ms=-1)
