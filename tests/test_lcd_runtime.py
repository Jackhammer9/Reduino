"""Unit tests for the host-side LCD runtime abstraction."""

from __future__ import annotations

import pytest

from Reduino.Displays import LCD


def test_lcd_parallel_alignment_and_progress() -> None:
    lcd = LCD(rs=12, en=11, d4=5, d5=4, d6=3, d7=2, cols=10, rows=2, backlight_pin=9)

    lcd.line(0, "Hi", align="center")
    lcd.write(0, 1, "Right", align="right", clear_row=False)
    lcd.progress(1, 50, max_value=100, width=5, label="Load")

    top, bottom = lcd.dump().splitlines()
    assert top == "    Hi    "
    assert bottom == "Load ██   "


def test_lcd_progress_styles_and_validation() -> None:
    lcd = LCD(rs=12, en=11, d4=5, d5=4, d6=3, d7=2, cols=8, rows=1)

    lcd.progress(0, 25, max_value=100, width=4, style="hash")
    line = lcd.dump().splitlines()[0]
    assert line[:4] == "#   "

    lcd.progress(0, 50, max_value=100, width=4, style="pipe", label="P")
    line = lcd.dump().splitlines()[0]
    assert line.startswith("P ")
    assert line[2:4] == "||"

    lcd.progress(0, 75, max_value=100, width=4, style="dot")
    line = lcd.dump().splitlines()[0]
    assert line[:4] == "... "

    with pytest.raises(ValueError):
        lcd.progress(0, 10, style="zigzag")


def test_lcd_runtime_animation_tick() -> None:
    lcd = LCD(i2c_addr=0x27, cols=5, rows=2)

    lcd.animate("scroll", 0, "ABC", speed_ms=0, loop=False)
    first_state = lcd.dump().splitlines()[0]
    lcd.tick(now_ms=1)
    lcd.tick(now_ms=2)
    second_state = lcd.dump().splitlines()[0]

    assert first_state == "ABC  "
    assert second_state == "BC   "


def test_lcd_brightness_constraints() -> None:
    lcd = LCD(rs=7, en=6, d4=5, d5=4, d6=3, d7=2, cols=16, rows=2)
    with pytest.raises(RuntimeError):
        lcd.brightness(128)

    with pytest.raises(RuntimeError):
        LCD(i2c_addr=0x27, cols=16, rows=2).brightness(200)

    with pytest.raises(ValueError):
        LCD(i2c_addr=0x27, rs=12, en=11, d4=5, d5=4, d6=3, d7=2)


def test_lcd_clear_and_glyph_storage() -> None:
    lcd = LCD(rs=12, en=11, d4=5, d5=4, d6=3, d7=2, cols=8, rows=2)

    lcd.line(0, "Hello")
    lcd.clear()
    assert lcd.dump().splitlines()[0] == "        "

    lcd.glyph(0, [0, 1, 2, 3, 4, 5, 6, 7])
    assert lcd.glyphs[0] == [0, 1, 2, 3, 4, 5, 6, 7]

    with pytest.raises(ValueError):
        lcd.glyph(8, [0] * 8)

    with pytest.raises(ValueError):
        lcd.glyph(0, [0, 1, 2])


def test_lcd_display_controls_backlight_state() -> None:
    lcd = LCD(rs=12, en=11, d4=5, d5=4, d6=3, d7=2, cols=16, rows=2, backlight_pin=9)

    lcd.display(False)
    assert not lcd.display_on
    assert not lcd.backlight_on

    lcd.backlight(False)
    lcd.display(True)
    assert lcd.display_on
    assert lcd.backlight_on

    panel = LCD(i2c_addr=0x27, cols=16, rows=2)
    panel.display(False)
    assert not panel.display_on
    assert not panel.backlight_on
