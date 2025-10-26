<p align="center">
  <img src="https://raw.githubusercontent.com/Jackhammer9/Reduino/refs/heads/main/.github/workflows/Reduino.png" alt="Reduino project illustration" width="320" />
</p>

# Reduino

Write expressive Python that turns into Arduino-flavoured C++ and optional PlatformIO
projects. Reduino lets you describe LED-centric sketches with familiar control flow,
transpiles the script into Arduino code, and (optionally) compiles/uploads it for you.

---

## Table of contents

- [Quick start](#quick-start)
- [How Reduino works](#how-reduino-works)
- [Supported devices & primitives](#supported-devices--primitives)
- [Supported Python features](#supported-python-features)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## Quick start

1. **Install dependencies**
   ```bash
   pip install -e .
   pip install platformio  # required for uploads
   ```
2. **Create a script**
   ```python
   from Reduino import target
   from Reduino.Actuators import Led
   from Reduino.Time import Sleep

   target("/dev/ttyACM0", upload=False)

   led = Led(13)
   for _ in range(3):
       led.toggle()
       Sleep(250)
   while True:
       led.toggle()
       Sleep(500)
   ```
3. **Run the script** – the transpiled C++ is printed and written into a temporary
   PlatformIO project. If `upload=True`, Reduino also calls `pio run -t upload` for you.

Generated projects target an Arduino Uno by default and live in a temporary folder. You can
re-run `pio run` manually to rebuild or flash again.

## How Reduino works

1. **Parsing** – `Reduino.transpile.parser.parse()` reads your Python script and builds an
   intermediate representation (`Program`, `LedDecl`, `Sleep`, etc.).
2. **Analysis** – literals and expressions are folded where possible (for example constant
   arithmetic or tuple unpacking), and control structures like `if`/`elif`/`else` are
   preserved in the IR.
3. **Emission** – `Reduino.transpile.emitter.emit()` turns the IR into Arduino-ready C++.
   Pin declarations create `pinMode` calls and global state, and sleep nodes become
   `delay()` statements.
4. **Toolchain integration** – `Reduino.target()` calls `emit(parse(src))`, prints the result,
   and uses the PlatformIO helpers in `Reduino.toolchain.pio` to write a `main.cpp` plus
   `platformio.ini` pointing at the requested serial port.

The pipeline keeps parsing/emission side-effect free so your host machine never drives
hardware directly—hardware interaction only happens once the generated sketch runs on the
board.

## Supported devices & primitives

| Primitive | Description | Key operations |
|-----------|-------------|----------------|
| `Reduino.Actuators.Led(pin=13)` | Represents a digital output LED. The helper mirrors the generated C++ and is safe to use in tests. | `.on()`, `.off()`, `.toggle()`, `.get_state()` |
| `Reduino.Time.Sleep(ms)` | Millisecond delay helper that can also execute waits on the host side. | `.wait()`, callable shortcut (e.g. `Sleep(500)()`) |
| `Reduino.target(port, upload=True)` | Transpile the calling module, emit C++, and optionally compile/upload with PlatformIO. | Prints generated code, writes a project, triggers `pio run`/`pio run -t upload` |

## Supported Python features

Reduino focuses on a lightweight DSL that feels like idiomatic Python while staying safe for
static analysis.

### Control flow

- `while True:` blocks become the Arduino `loop()` body.
- `for i in range(N):` loops at top-level unroll into repeated setup statements.
- `if` / `elif` / `else` constructs are preserved with their conditions.

### Variables & assignments

- Regular assignments, tuple unpacking, and reassignments in setup scope create matching C++
  declarations.
- Branch-local assignments are promoted to globals so both sides of an `if` can mutate them
  safely.

### Expressions & built-ins

- Integer, float, string, and boolean literals.
- Arithmetic, bitwise, boolean, and comparison operators.
- Safe casts: `int()`, `float()`, `bool()`, `str()`.
- Built-ins: `len()`, `abs()`, `max()`, `min()` (with helper snippets emitted automatically).

### Device primitives

- Instantiate LEDs with literal pins or symbolic expressions; actions translate to
  `digitalWrite` calls (`HIGH`, `LOW`, and toggled states are handled automatically).
- Sleep expressions become `delay(ms)` even when the argument is symbolic.

### Target directive

- `target("PORT")` can appear anywhere at top level; the last call wins and is written into
  `platformio.ini`.

## Testing

Install the optional development dependencies and run the test suite:

```bash
pip install -e .[dev]
pytest
```

The tests exercise parser behaviour, code generation, runtime helpers, and the public
actuator/time primitives.

## Contributing

We welcome new actuators, sensors, and improvements to the transpiler. See
[CONTRIBUTING.md](CONTRIBUTING.md) for a detailed guide.

## License

Reduino is released under the **GNU General Public License v3.0 (GPL-3.0)**.

This means you are free to:
- Use, modify, and distribute Reduino under the terms of the GPL-3.0.
- Build upon it in your own open-source projects, provided your derivative works remain open-source under the same license.

However, if you would like to:
- Use Reduino in a **closed-source**, **commercial**, or **proprietary** product,
- Obtain a **custom or dual license** for integration in commercial environments,

please reach out for licensing options:

📧 **Commercial inquiries:** arnavbajaj9@gmail.com

---

© 2025 Arnav Bajaj. All rights reserved.
