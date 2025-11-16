# Contributing to Reduino

Thank you for your interest in improving **Reduino**!  
This document explains how to set up your environment, the expected workflow, and the process for safely extending Reduino with new devices, syntax, or utilities.

---

## Overview

Reduino is a **Python → Arduino C++ transpiler** that enables developers to control hardware using high-level Python syntax.  
To keep this experience consistent, contributions must follow clean code patterns, consistent naming, and test coverage.

---

## Getting Started

### 1. Fork & Clone

```bash
git clone https://github.com/Jackhammer9/Reduino.git
cd Reduino
```
2. Create a Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate   # on Linux/macOS
.venv\Scripts\activate      # on Windows
```
3. Install Dependencies
```bash
pip install -e .[dev]
pip install platformio      # required for upload testing
```
4. Run Tests
Reduino uses pytest for its test suite.

```bash
pytest
```
Make sure all tests pass before committing.

# Repository Layout
```graphql
src/Reduino/
├── Actuators/         # LED, Buzzer, Servo, etc.
├── Displays/          # LCD and other visual outputs
├── Sensors/           # Ultrasonic, Button, Potentiometer, etc.
├── Communication/     # SerialMonitor and future I/O classes
├── Utils/             # Timing helpers (sleep, map)
├── toolchain/         # PlatformIO integration
└── transpile/         # Parser, Emitter, AST, and core transpiler
```

# Development Workflow
Create a new branch for your feature or fix:

```bash
git checkout -b feature/my-new-sensor
Implement your feature under the appropriate module.
```

Add or update tests under tests/.

Update documentation in README.md and CONTRIBUTING.md if necessary.

Run all tests to verify correctness.

Submit a Pull Request with a clear description and examples.

# Code Style Guidelines
General
Use PEP 8 conventions for Python.

Use camelCase only in emitted Arduino C++ code.

Avoid external dependencies unless absolutely required.

Keep code minimal and deterministic  the transpiler must never execute user logic on the host.

Naming
Follow the existing naming convention:

Purpose	Example
Declaration node	LedDecl, ButtonDecl
Action node	LedOn, BuzzerMelody, ServoWrite
Class name (Python)	Led, Buzzer, Servo, Ultrasonic
File name	lowercase: led.py, buzzer.py

# Adding a New Device (Actuator / Sensor / Display)
Reduino uses an IR (Intermediate Representation) between Python and C++.

To add new hardware, follow these steps carefully.

1. Plan the API
Example for a new device:

```python
from Reduino.Actuators import Motor

motor = Motor(5, 6)
motor.forward(speed=150)
motor.stop()
```
Decide what actions it will have (forward, reverse, stop, etc.) and which Arduino headers it needs (Servo.h, Wire.h, etc.).

2. Extend the AST (src/Reduino/transpile/ast.py)
Add new dataclasses that describe both the declaration and actions.

```python
@dataclass
class MotorDecl:
    name: str
    pin1: Union[int, str]
    pin2: Union[int, str]

@dataclass
class MotorForward:
    name: str
    speed: Union[int, str]
Use Decl for initialization and <Device><Verb> for actions.
```

3. Update the Parser (src/Reduino/transpile/parser.py)
Add import recognition:

```python
if module == "Reduino.Actuators" and name == "Motor":
    return None
```
Add regex patterns for declaration and actions.

Evaluate constants using _eval_const() when possible.

Return appropriate IR node objects.

4. Update the Emitter (src/Reduino/transpile/emitter.py)
Implement C++ emission for the new nodes:

Emit setup code (pinMode, object creation)

Emit runtime code for actions

Inject Arduino headers when necessary

```python
if isinstance(node, MotorForward):
    lines.append(f"analogWrite({pin1}, {speed});")
    lines.append(f"analogWrite({pin2}, 0);")
```
Add new helper variables for state tracking if needed.

5. Add Runtime Python Helper (Optional)
If your device needs a Python-side placeholder for syntax (e.g., Motor.forward()), add it under:

```bash
src/Reduino/Actuators/motor.py
```
Example:

```python
class Motor:
    def __init__(self, pin1, pin2):
        self.pin1 = pin1
        self.pin2 = pin2
```
Host-side methods don’t perform real actions they only exist for syntax and transpilation.

6. Register the Device

Add the new class to the appropriate `__init__.py` (e.g. `src/Reduino/Displays/__init__.py`) so users can import it. If the hardware needs additional PlatformIO libraries, update `_collect_required_libraries()` in `src/Reduino/__init__.py`.

7. Write Tests
Parser Test (tests/test_parser.py)
Ensure Reduino recognizes your new device:

```python
code = "from Reduino.Actuators import Motor\nmotor = Motor(5,6)\nmotor.forward(100)"
prog = parse(code)
assert any(isinstance(n, MotorDecl) for n in prog.body)
```

Emitter Test (tests/test_emitter.py)
Verify correct Arduino code emission:

```python
cpp = emit(parse(code))
assert "analogWrite" in cpp
```

8. Documentation & Examples
Update README.md with:

A short table of methods and parameters

A working example including target() at top

Any special notes ([!NOTE] blocks)

Add an example script under:

```bash
examples/Motor/motor_demo.py
```

# Testing & QA
Run pytest before every commit.

Use short, descriptive commit messages (e.g., “Add RGB LED fade support”).

Lint with ruff or flake8.

# Contribution Tips
Keep PRs small and focused. Avoid combining multiple feature additions in one PR.

Write docstrings for all new public functions and classes.

Test on real hardware whenever possible to confirm the generated code works.

Discuss before large refactors. Open an issue to gather feedback first.

# Pull Request Checklist
 Code follows project conventions

 All tests pass (pytest)

 Examples updated or added

 README and Contributing docs updated

 PlatformIO upload verified if applicable

Happy hacking with Reduino!
