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
class LedDecl:
    """Declare an LED instance bound to ``pin``."""

    name: str
    pin: Union[int, str] = 13


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
    count: int
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
