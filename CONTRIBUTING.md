# Contributing to Reduino

Thanks for helping Reduino grow! This guide explains how to set up your development
environment, the expectations for pull requests, and provides a detailed recipe for adding new
actuators or sensors to the transpiler.

---

## Getting started

1. **Clone and create a virtual environment**
   ```bash
   git clone <your-fork-url>
   cd Reduino
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   ```
2. **Install the project with the development extras**
   ```bash
   pip install -e .[dev]
   ```
3. **Install PlatformIO if you plan to test uploads**
   ```bash
   pip install platformio
   ```

## Development workflow

- **Write tests** for new behaviour and keep existing tests passing:
  ```bash
  pytest
  ```
- **Keep commits focused.** Each pull request should have a clear purpose and include any
  documentation updates that help users understand the change.
- **Document user-facing additions** in `README.md`, and update examples when new primitives or
  syntax are introduced.
- **Run PlatformIO manually** (`pio run`, `pio run -t upload`) when your change affects the
  generated C++ or project layout.

## Code style and guidelines

- Follow the existing module layout under `src/Reduino/`:
  ```
  src/Reduino/
    transpile/      # Parser, AST, and emitter
    toolchain/      # PlatformIO helpers
    Actuators.py    # Runtime helpers mirroring generated code
    Time.py         # Timing helpers for tests/examples
  ```
- Prefer descriptive naming (`LedDecl`, `Sleep`, `VarAssign`) and keep parser/emitter logic
  side-effect free. The transpiler must never execute user code.
- Use Python `snake_case` for variables/functions and match Arduino C++ conventions (camelCase
  for temporary loop variables when appropriate) in emitted code.
- Avoid introducing heavy runtime dependencies. Keep third-party tools in optional extras.

## Adding new actuators or sensors

The transpiler is IR-driven: the parser recognises Python syntax and produces IR nodes, and the
emitter converts those nodes into Arduino C++. The checklist below keeps both halves aligned.

### 1. Plan the feature

- Pick the category: **Actuator** (outputs such as LEDs, buzzers, motors) or **Sensor**
  (inputs such as ultrasonic sensors or IMUs).
- Sketch the Python API you want users to write. Example:
  ```python
  from Reduino.Actuators import Buzzer
  buzzer = Buzzer(9)
  buzzer.on(440)
  buzzer.off()
  ```
- Decide which Arduino headers and setup steps are required (`<Servo.h>`, `Wire.begin()`, etc.).

### 2. Extend the IR (`src/Reduino/transpile/ast.py`)

Add dataclasses describing declarations and actions:
```python
from dataclasses import dataclass
from typing import Union

@dataclass
class BuzzerDecl:
    name: str
    pin: Union[int, str]

@dataclass
class BuzzerOn:
    name: str
    freq: Union[int, str]

@dataclass
class BuzzerOff:
    name: str
```
Use the naming convention `<Device>Decl`, `<Device><Verb>` to mirror existing nodes.

### 3. Update the parser (`src/Reduino/transpile/parser.py`)

1. **Ignore imports** for the new device so users can `from Reduino.Actuators import Buzzer`.
2. **Recognise declarations and actions** with new regular expressions.
3. **Evaluate constant expressions** via `_eval_const` where possible; fall back to `_to_c_expr`
   to keep symbolic expressions intact.
4. **Record helper requirements** (e.g. custom headers) by adding entries to the context’s
   `helpers` set if the emitted code needs them.

### 4. Update the emitter (`src/Reduino/transpile/emitter.py`)

- Emit global state, setup code, and action statements for the new nodes.
- Inject additional headers or helper functions if your device requires them (e.g. servo
  objects, wire initialisation).
- Ensure pin initialisation happens inside `setup()` even when declarations appear in the loop
  body.

### 5. Tests

- Add parser tests (`tests/test_parser.py`) covering declarations, actions, control-flow
  interactions, and helper promotion.
- Add emitter tests (`tests/test_emitter.py`) that confirm the expected C++ output (pin modes,
  library includes, method calls, etc.).
- Extend runtime helper tests (`tests/test_actuators.py`, `tests/test_time.py`) when new Python
  classes are introduced.

### 6. Documentation & examples

- Provide usage examples under `examples/<device>/` that mirror the intended Python DSL.
- Update `README.md` and this document when the feature adds new primitives, syntax, or
  requirements.

### 7. Pull request checklist

- [ ] IR dataclasses added.
- [ ] Parser recognises imports, declarations, and actions.
- [ ] Emitter produces the correct C++ (including headers/setup).
- [ ] Tests cover parser, emitter, and runtime helpers.
- [ ] Documentation and examples updated.
- [ ] `pytest` (and `pio run` if applicable) succeed locally.

Happy hacking!
