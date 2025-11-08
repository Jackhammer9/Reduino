"""In-memory abstraction of an HD44780 style character LCD."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict, List, Optional, Sequence

_ALIGN_OPTIONS = {"left", "center", "right"}


@dataclass
class _AnimationState:
    """Runtime bookkeeping for non-blocking text animations."""

    animation: str
    row: int
    text: str
    speed_ms: int
    loop: bool
    last_tick: int = 0
    offset: int = 0
    active: bool = True
    direction: int = 1
    visible: int = 0
    show: bool = True
    cycles: int = 0


class LCD:
    """Python-side mirror of the transpiled LCD API."""

    def __init__(
        self,
        *,
        rs: Optional[int] = None,
        en: Optional[int] = None,
        d4: Optional[int] = None,
        d5: Optional[int] = None,
        d6: Optional[int] = None,
        d7: Optional[int] = None,
        cols: int = 16,
        rows: int = 2,
        rw: Optional[int] = None,
        backlight_pin: Optional[int] = None,
        i2c_addr: Optional[int] = None,
    ) -> None:
        """Create a new LCD abstraction.

        Parameters
        ----------
        rs, en, d4, d5, d6, d7:
            Parallel control/data pins when using the 4-bit interface.
        cols, rows:
            Dimensions of the LCD.
        rw:
            Optional RW pin for parallel mode.
        backlight_pin:
            Optional PWM pin for brightness control in parallel mode.
        i2c_addr:
            I²C backpack address. When provided the LCD operates in
            backpack mode and parallel pin arguments must be omitted.
        """

        self.cols = int(cols)
        self.rows = int(rows)
        if self.cols <= 0 or self.rows <= 0:
            raise ValueError("cols and rows must be positive")

        self.is_i2c = i2c_addr is not None
        if self.is_i2c:
            if any(pin is not None for pin in (rs, en, d4, d5, d6, d7, rw)):
                raise ValueError("parallel pins are not supported in I2C mode")
            self.i2c_addr = int(i2c_addr)
            self.pins: Dict[str, Optional[int]] = {"backlight": backlight_pin}
        else:
            required = [rs, en, d4, d5, d6, d7]
            if any(pin is None for pin in required):
                raise ValueError("parallel mode requires rs, en, d4, d5, d6 and d7 pins")
            self.pins = {
                "rs": int(rs),
                "en": int(en),
                "d4": int(d4),
                "d5": int(d5),
                "d6": int(d6),
                "d7": int(d7),
                "rw": None if rw is None else int(rw),
                "backlight": None if backlight_pin is None else int(backlight_pin),
            }
            self.i2c_addr = None

        self.backlight_pin = backlight_pin
        self.display_on = True
        self.backlight_on = True
        self.brightness_level = 255
        self.glyphs: Dict[int, List[int]] = {}
        self.animations: Dict[str, _AnimationState] = {}
        self.buffer: List[str] = [" " * self.cols for _ in range(self.rows)]
        self.begin()

    def begin(self) -> None:
        """Initialise the backing buffer and reset animation state."""

        self.buffer = [" " * self.cols for _ in range(self.rows)]
        self.display_on = True
        self.backlight_on = True
        self.brightness_level = 255
        self.animations.clear()

    # --- Helpers -----------------------------------------------------------------
    def _validate_row(self, row: int) -> int:
        row_idx = int(row)
        if not 0 <= row_idx < self.rows:
            raise ValueError("row out of bounds")
        return row_idx

    @staticmethod
    def _resolve_align(label: str) -> str:
        align = label.lower()
        if align not in _ALIGN_OPTIONS:
            raise ValueError("align must be 'left', 'center' or 'right'")
        return align

    def _place_text(self, row: int, text: str, align: str, start_col: int = 0) -> None:
        row_idx = self._validate_row(row)
        content = str(text)
        align_value = self._resolve_align(align)
        available_width = max(0, self.cols - max(0, int(start_col)))
        if available_width <= 0:
            return
        if len(content) > available_width:
            content = content[:available_width]
        if align_value == "left":
            col = int(start_col)
        elif align_value == "right":
            col = int(start_col) + (available_width - len(content))
        else:  # center
            col = int(start_col) + (available_width - len(content)) // 2
        col = max(int(start_col), min(self.cols - len(content), col))
        line = list(self.buffer[row_idx])
        for offset, char in enumerate(content):
            if 0 <= col + offset < self.cols:
                line[col + offset] = char
        self.buffer[row_idx] = "".join(line)

    # --- Core text primitives ----------------------------------------------------
    def clear(self) -> None:
        """Erase the entire display buffer."""

        self.buffer = [" " * self.cols for _ in range(self.rows)]

    def line(
        self,
        row: int,
        text: str,
        *,
        align: str = "left",
        clear_row: bool = True,
    ) -> None:
        """Write ``text`` to ``row`` using alignment rules."""

        row_idx = self._validate_row(row)
        if clear_row:
            self.buffer[row_idx] = " " * self.cols
        self._place_text(row_idx, text, align, 0)

    def write(
        self,
        col: int,
        row: int,
        text: str,
        *,
        clear_row: bool = True,
        align: str = "left",
    ) -> None:
        """Write ``text`` starting at column ``col`` on ``row``."""

        row_idx = self._validate_row(row)
        if clear_row:
            self.buffer[row_idx] = " " * self.cols
        self._place_text(row_idx, text, align, int(col))

    def message(
        self,
        top: Optional[str] = None,
        bottom: Optional[str] = None,
        *,
        top_align: str = "left",
        bottom_align: str = "left",
        clear_rows: bool = True,
    ) -> None:
        """Convenience helper for two-line displays."""

        if top is not None:
            self.line(0, top, align=top_align, clear_row=clear_rows)
        if bottom is not None and self.rows > 1:
            self.line(1, bottom, align=bottom_align, clear_row=clear_rows)

    def display(self, on: bool) -> None:
        """Toggle the simulated display power state."""

        state = bool(on)
        self.display_on = state
        self.backlight_on = state

    def backlight(self, on: bool) -> None:
        """Toggle the simulated backlight state."""

        self.backlight_on = bool(on)

    def brightness(self, level: int) -> None:
        """Adjust the PWM brightness level in parallel mode."""

        if self.is_i2c:
            raise RuntimeError("brightness control is only available in parallel mode")
        if self.backlight_pin is None:
            raise RuntimeError("brightness requires backlight_pin")
        if not 0 <= int(level) <= 255:
            raise ValueError("brightness must be between 0 and 255")
        self.brightness_level = int(level)

    # --- Widgets -----------------------------------------------------------------
    def glyph(self, slot: int, bitmap: Sequence[int]) -> None:
        """Register a custom glyph bitmap for ``slot``."""

        if not 0 <= int(slot) <= 7:
            raise ValueError("slot must be within 0-7")
        values = [int(value) & 0x1F for value in bitmap][:8]
        if len(values) != 8:
            raise ValueError("bitmap must contain 8 rows")
        self.glyphs[int(slot)] = values

    _PROGRESS_STYLES: ClassVar[Dict[str, str]] = {
        "block": "█",
        "hash": "#",
        "pipe": "|",
        "dot": ".",
    }

    def progress(
        self,
        row: int,
        value: int,
        max_value: int = 100,
        *,
        width: Optional[int] = None,
        style: str = "block",
        label: Optional[str] = None,
    ) -> None:
        """Render a basic horizontal progress bar."""

        style_key = str(style).lower()
        try:
            glyph = self._PROGRESS_STYLES[style_key]
        except KeyError as exc:
            allowed = ", ".join(sorted(self._PROGRESS_STYLES))
            raise ValueError(f"unsupported progress style: {style!r} (choose from {allowed})") from exc
        row_idx = self._validate_row(row)
        total_width = self.cols if width is None else max(1, min(self.cols, int(width)))
        ratio = 0 if max_value <= 0 else max(0.0, min(1.0, float(value) / float(max_value)))
        filled = int(round(ratio * total_width))
        empty = max(0, total_width - filled)
        bar = glyph * filled + " " * empty
        if label:
            text = f"{label} {bar}"[: self.cols]
        else:
            text = bar[: self.cols]
        self.buffer[row_idx] = text.ljust(self.cols)

    # --- Animations --------------------------------------------------------------
    _ANIMATION_OPTIONS: ClassVar[Dict[str, str]] = {
        "scroll": "Marquee-style horizontal scroll",
        "blink": "Toggle text visibility without blocking",
        "typewriter": "Reveal text one character at a time",
        "bounce": "Slide text left and right across the row",
    }

    def animate(
        self,
        animation: str,
        row: int,
        text: str,
        *,
        speed_ms: int = 200,
        loop: bool = False,
    ) -> None:
        """Start or restart a named LCD animation."""

        animation_name = str(animation).lower()
        if animation_name not in self._ANIMATION_OPTIONS:
            options = ", ".join(sorted(self._ANIMATION_OPTIONS))
            raise ValueError(
                f"unsupported animation: {animation!r} (choose from {options})"
            )
        row_idx = self._validate_row(row)
        state = _AnimationState(
            animation=animation_name,
            row=row_idx,
            text=str(text),
            speed_ms=max(0, int(speed_ms)),
            loop=bool(loop),
            last_tick=0,
            offset=0,
            active=True,
            direction=1,
            visible=0,
            show=True,
            cycles=0,
        )
        key = f"{animation_name}:{row_idx}:{len(self.animations)}"
        self.animations[key] = state

        if animation_name == "scroll":
            self.line(row_idx, state.text[: self.cols], align="left", clear_row=True)
        elif animation_name == "blink":
            state.show = True
            view = state.text[: self.cols]
            self.line(row_idx, view, align="left", clear_row=True)
        elif animation_name == "typewriter":
            length = len(state.text)
            state.visible = min(length, 1)
            snippet = state.text[: state.visible][: self.cols]
            self.line(row_idx, snippet, align="left", clear_row=True)
        elif animation_name == "bounce":
            state.direction = 1
            state.offset = 0
            state.show = False
            row_chars = [" "] * self.cols
            for index, char in enumerate(state.text):
                if index >= self.cols:
                    break
                row_chars[index] = char
            self.buffer[row_idx] = "".join(row_chars)

        else:  # pragma: no cover - defensive fallback
            raise AssertionError(f"unhandled animation {animation_name}")

    def tick(self, now_ms: Optional[int] = None) -> None:
        """Advance any running animations."""

        if now_ms is None:
            now_ms = 0
        for state in list(self.animations.values()):
            if not state.active:
                continue
            if state.speed_ms <= 0:
                proceed = True
            else:
                if state.last_tick and now_ms - state.last_tick < state.speed_ms:
                    continue
                proceed = True
            if not proceed:
                continue
            state.last_tick = now_ms
            if state.animation == "scroll":
                padded = state.text + " " * self.cols
                if not padded:
                    continue
                view = (padded + padded)[state.offset : state.offset + self.cols]
                self.line(state.row, view, clear_row=True)
                state.offset += 1
                if state.offset >= len(padded):
                    if state.loop:
                        state.offset = 0
                    else:
                        state.active = False
            elif state.animation == "blink":
                state.show = not state.show
                if state.show:
                    view = state.text[: self.cols]
                    self.line(state.row, view, align="left", clear_row=True)
                else:
                    self.line(state.row, "", align="left", clear_row=True)
                    state.cycles += 1
                    if not state.loop:
                        state.active = False
            elif state.animation == "typewriter":
                length = len(state.text)
                if length == 0:
                    self.line(state.row, "", align="left", clear_row=True)
                    state.active = state.loop
                    continue
                if state.visible < length:
                    state.visible += 1
                    snippet = state.text[: state.visible][: self.cols]
                    self.line(state.row, snippet, align="left", clear_row=True)
                    if state.visible >= length and not state.loop:
                        state.active = False
                else:
                    if state.loop:
                        state.visible = 0
                        self.line(state.row, "", align="left", clear_row=True)
                    else:
                        state.active = False
            elif state.animation == "bounce":
                text = state.text
                if not text:
                    self.line(state.row, "", align="left", clear_row=True)
                    state.active = state.loop
                    continue
                if len(text) >= self.cols:
                    view = text[: self.cols]
                    self.line(state.row, view, align="left", clear_row=True)
                    state.active = state.loop
                    continue
                max_offset = max(0, self.cols - len(text))
                if max_offset == 0:
                    state.active = state.loop
                    continue
                state.offset += state.direction
                if state.offset >= max_offset:
                    state.offset = max_offset
                    state.direction = -1
                    state.show = True
                elif state.offset <= 0:
                    state.offset = 0
                    state.direction = 1
                    if state.show:
                        state.cycles += 1
                        state.show = False
                        if not state.loop and state.cycles >= 1:
                            state.active = False
                row_chars = [" "] * self.cols
                for index, char in enumerate(text):
                    position = state.offset + index
                    if position >= self.cols:
                        break
                    row_chars[position] = char
                self.buffer[state.row] = "".join(row_chars)
            else:  # pragma: no cover - defensive fallback
                raise AssertionError(f"unknown animation type {state.animation}")

    # --- Representation helpers --------------------------------------------------
    def dump(self) -> str:
        """Return the simulated display contents as a string."""

        return "\n".join(self.buffer)

    def __repr__(self) -> str:  # pragma: no cover - diagnostic helper
        mode = "I2C" if self.is_i2c else "parallel"
        return f"LCD(mode={mode!r}, cols={self.cols}, rows={self.rows})"
