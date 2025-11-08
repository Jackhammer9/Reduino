"""AST node definitions shared by the parser and emitter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple, Union


@dataclass
class Program:
    """Container for a transpiled program."""

    setup_body: List[object] = field(default_factory=list)
    loop_body: List[object] = field(default_factory=list)
    target_port: Optional[str] = None
    global_decls: List[object] = field(default_factory=list)
    helpers: Set[str] = field(default_factory=set)
    functions: List["FunctionDef"] = field(default_factory=list)
    ultrasonic_measurements: Set[str] = field(default_factory=set)


@dataclass
class ButtonDecl:
    """Declare a button input bound to ``pin`` with an optional callback."""

    name: str
    pin: Union[int, str]
    on_click: Optional[str] = None
    mode: str = "INPUT_PULLUP"


@dataclass
class ButtonPoll:
    """Poll a button input and dispatch its callback when pressed."""

    name: str


@dataclass
class PotentiometerDecl:
    """Declare an analogue potentiometer input bound to ``pin``."""

    name: str
    pin: str


@dataclass
class LCDDecl:
    """Declare an HD44780 compatible LCD display."""

    name: str
    cols: Union[int, str]
    rows: Union[int, str]
    interface: str = "parallel"
    rs: Optional[Union[int, str]] = None
    en: Optional[Union[int, str]] = None
    d4: Optional[Union[int, str]] = None
    d5: Optional[Union[int, str]] = None
    d6: Optional[Union[int, str]] = None
    d7: Optional[Union[int, str]] = None
    rw: Optional[Union[int, str]] = None
    backlight_pin: Optional[Union[int, str]] = None
    i2c_addr: Optional[Union[int, str]] = None


@dataclass
class LCDWrite:
    """Write ``text`` to a specific column/row on the LCD."""

    name: str
    col: Union[int, str]
    row: Union[int, str]
    text: str
    clear_row: Union[bool, str] = True
    align: str = "left"


@dataclass
class LCDMessage:
    """Write optional messages to the first two LCD rows."""

    name: str
    top: Optional[str] = None
    bottom: Optional[str] = None
    top_align: str = "left"
    bottom_align: str = "left"
    clear_rows: Union[bool, str] = True


@dataclass
class LCDLine:
    """Write text to a single LCD row."""

    name: str
    row: Union[int, str]
    text: str
    align: str = "left"
    clear_row: Union[bool, str] = True


@dataclass
class LCDClear:
    """Clear the LCD."""

    name: str


@dataclass
class LCDDisplay:
    """Toggle the LCD display visibility."""

    name: str
    on: Union[bool, str]


@dataclass
class LCDBacklight:
    """Toggle the LCD backlight."""

    name: str
    on: Union[bool, str]


@dataclass
class LCDBrightness:
    """Adjust LCD backlight brightness."""

    name: str
    level: Union[int, str]


@dataclass
class LCDGlyph:
    """Register a custom glyph bitmap."""

    name: str
    slot: Union[int, str]
    bitmap: List[int]


@dataclass
class LCDProgress:
    """Render a progress bar on the LCD."""

    name: str
    row: Union[int, str]
    value: Union[int, str]
    max_value: Union[int, str] = 100
    width: Optional[Union[int, str]] = None
    style: str = "block"
    label: Optional[str] = None


@dataclass
class LCDAnimate:
    """Start a non-blocking LCD animation."""

    name: str
    animation: str
    row: Union[int, str]
    text: str
    speed_ms: Union[int, str] = 200
    loop: Union[bool, str] = False


@dataclass
class LCDTick:
    """Advance LCD animations within loop()."""

    name: str


@dataclass
class LedDecl:
    """Declare an LED instance bound to ``pin``."""

    name: str
    pin: Union[int, str] = 13


@dataclass
class BuzzerDecl:
    """Declare a passive buzzer bound to ``pin``."""

    name: str
    pin: Union[int, str] = 8
    default_frequency: Union[float, int, str] = 440.0


@dataclass
class BuzzerPlayTone:
    """Play a tone on the passive buzzer."""

    name: str
    frequency: Union[float, int, str]
    duration_ms: Optional[Union[float, int, str]] = None


@dataclass
class BuzzerStop:
    """Stop any active tone on the buzzer."""

    name: str


@dataclass
class BuzzerBeep:
    """Emit a pulsed tone pattern on the buzzer."""

    name: str
    frequency: Optional[Union[float, int, str]] = None
    on_ms: Union[float, int, str] = 100
    off_ms: Union[float, int, str] = 100
    times: Union[int, str] = 1


@dataclass
class BuzzerSweep:
    """Sweep the buzzer between start and end frequencies."""

    name: str
    start_hz: Union[float, int, str]
    end_hz: Union[float, int, str]
    duration_ms: Union[float, int, str]
    steps: Union[int, str] = 10


@dataclass
class BuzzerMelody:
    """Play a named cue melody on the buzzer."""

    name: str
    melody: str
    tempo: Optional[Union[float, int, str]] = None


@dataclass
class LedOn:
    """Turn the named LED on."""

    name: str


@dataclass
class LedOff:
    """Turn the named LED off."""

    name: str


@dataclass
class LedToggle:
    """Toggle the named LED state."""

    name: str


@dataclass
class LedSetBrightness:
    """Update the PWM brightness value for the LED."""

    name: str
    value: Union[int, str]


@dataclass
class LedBlink:
    """Blink the LED with an on/off delay pattern."""

    name: str
    duration_ms: Union[int, str]
    times: Union[int, str] = 1


@dataclass
class LedFadeIn:
    """Gradually increase LED brightness to full."""

    name: str
    step: Union[int, str]
    delay_ms: Union[int, str]


@dataclass
class LedFadeOut:
    """Gradually decrease LED brightness to off."""

    name: str
    step: Union[int, str]
    delay_ms: Union[int, str]


@dataclass
class LedFlashPattern:
    """Drive the LED using an explicit flash sequence."""

    name: str
    pattern: List[int]
    delay_ms: Union[int, str]


@dataclass
class RGBLedDecl:
    """Declare an RGB LED instance bound to three PWM pins."""

    name: str
    red_pin: Union[int, str]
    green_pin: Union[int, str]
    blue_pin: Union[int, str]


@dataclass
class RGBLedSetColor:
    """Update the RGB LED to the provided colour components."""

    name: str
    red: Union[int, str]
    green: Union[int, str]
    blue: Union[int, str]


@dataclass
class RGBLedOn:
    """Switch the RGB LED on using the provided colour intensities."""

    name: str
    red: Union[int, str]
    green: Union[int, str]
    blue: Union[int, str]


@dataclass
class RGBLedOff:
    """Switch the RGB LED off."""

    name: str


@dataclass
class RGBLedFade:
    """Fade the RGB LED towards a colour over a duration."""

    name: str
    red: Union[int, str]
    green: Union[int, str]
    blue: Union[int, str]
    duration_ms: Union[int, str]
    steps: Union[int, str]


@dataclass
class RGBLedBlink:
    """Blink the RGB LED with a colour and delay."""

    name: str
    red: Union[int, str]
    green: Union[int, str]
    blue: Union[int, str]
    times: Union[int, str]
    delay_ms: Union[int, str]


@dataclass
class ServoDecl:
    """Declare a hobby servo bound to ``pin`` with optional calibration."""

    name: str
    pin: Union[int, str] = 9
    min_angle: Union[float, int, str] = 0.0
    max_angle: Union[float, int, str] = 180.0
    min_pulse_us: Union[float, int, str] = 544.0
    max_pulse_us: Union[float, int, str] = 2400.0


@dataclass
class ServoWrite:
    """Command the servo to move to an angle in degrees."""

    name: str
    angle: Union[float, int, str]


@dataclass
class ServoWriteMicroseconds:
    """Command the servo using a pulse width in microseconds."""

    name: str
    pulse_us: Union[float, int, str]


@dataclass
class Sleep:
    """Delay execution for ``ms`` milliseconds."""

    ms: Union[int, str]


@dataclass
class SerialMonitorDecl:
    """Declare a serial monitor configuration with a baud rate."""

    name: str
    baud: Union[int, str] = 9600


@dataclass
class SerialWrite:
    """Emit data to the serial monitor."""

    name: str
    value: str
    newline: bool = True


@dataclass
class UltrasonicDecl:
    """Declare an ultrasonic sensor bound to ``trig``/``echo`` pins."""

    name: str
    trig: Union[int, str]
    echo: Union[int, str]
    model: str = "HC-SR04"


@dataclass
class VarDecl:
    """Declare a variable with an optional initializer."""

    name: str
    c_type: str
    expr: str
    global_scope: bool = False


@dataclass
class VarAssign:
    """Assign a new value to an existing variable."""

    name: str
    expr: str


@dataclass
class ExprStmt:
    """A standalone expression that should be evaluated for side effects."""

    expr: str


@dataclass
class ConditionalBranch:
    """One branch of a conditional statement."""

    condition: str
    body: List[object] = field(default_factory=list)


@dataclass
class IfStatement:
    """An ``if``/``elif``/``else`` conditional block."""

    branches: List[ConditionalBranch] = field(default_factory=list)
    else_body: List[object] = field(default_factory=list)


@dataclass
class WhileLoop:
    """A ``while`` loop with a condition and body."""

    condition: str
    body: List[object] = field(default_factory=list)


@dataclass
class ForRangeLoop:
    """A ``for`` loop over ``range(count)`` with a loop variable."""

    var_name: str
    count: Union[int, str]
    body: List[object] = field(default_factory=list)


@dataclass
class BreakStmt:
    """A ``break`` statement used to exit the innermost loop."""

    pass


@dataclass
class CatchClause:
    """A ``catch`` clause attached to a :class:`TryStatement`."""

    exception: Optional[str] = None
    target: Optional[str] = None
    body: List[object] = field(default_factory=list)


@dataclass
class TryStatement:
    """A ``try`` block with one or more ``catch`` handlers."""

    try_body: List[object] = field(default_factory=list)
    handlers: List[CatchClause] = field(default_factory=list)


@dataclass
class ReturnStmt:
    """A ``return`` statement within a function body."""

    expr: Optional[str] = None


@dataclass
class FunctionDef:
    """Representation of a helper function defined in the source."""

    name: str
    params: List[Tuple[str, str]] = field(default_factory=list)
    body: List[object] = field(default_factory=list)
    return_type: str = "void"
