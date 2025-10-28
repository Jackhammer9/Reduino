<div align="center">
  <img src="https://raw.githubusercontent.com/Jackhammer9/Reduino/refs/heads/main/.github/workflows/Reduino.png" alt="Reduino" width="360" />

  <h1>Reduino</h1>
  <p><em>Write friendly Python. Get Arduino-ready C++. Upload Easily.</em></p>

  <!-- Badges -->

  <a href="https://www.gnu.org/licenses/gpl-3.0">
    <img alt="License" src="https://img.shields.io/badge/License-GPLv3-blueviolet" />
  </a>
  <a href="https://github.com/Jackhammer9/Reduino/stargazers">
    <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/Jackhammer9/Reduino?logo=Github" />
  </a>
  <a href="https://github.com/Jackhammer9/Reduino/network/members">
    <img alt="GitHub forks" src="https://img.shields.io/github/forks/Jackhammer9/Reduino?color=red&logo=Github&style=flat-square" />
  </a>
  <a href="https://github.com/Jackhammer9/Reduino/watchers">
    <img alt="GitHub watchers" src="https://img.shields.io/github/watchers/Jackhammer9/Reduino?logo=Github" />
  </a>
  <a href="https://github.com/Jackhammer9">
    <img alt="GitHub followers" src="https://img.shields.io/github/followers/Jackhammer9?logo=Github" />
  </a>
  <a href="https://github.com/Jackhammer9/Reduino/pulls?q=is%3Apr+is%3Aclosed">
    <img alt="Closed PRs" src="https://img.shields.io/github/issues-pr-closed/Jackhammer9/Reduino?logo=Github" />
  </a>
  <a href="https://github.com/Jackhammer9/Reduino/issues?q=is%3Aissue+is%3Aclosed">
    <img alt="Closed issues" src="https://img.shields.io/github/issues-closed/Jackhammer9/Reduino?logo=Github" />
  </a>
  <a href="https://github.com/Jackhammer9/Reduino">
    <img alt="Repo size" src="https://img.shields.io/github/repo-size/Jackhammer9/Reduino?logo=Github" />
  </a>
  <a href="https://github.com/Jackhammer9/Reduino/releases/latest">
    <img alt="Latest release" src="https://img.shields.io/github/v/release/Jackhammer9/Reduino?display_name=tag&logo=Github" />
  </a>
  <a href="https://pypi.org/project/Reduino/">
    <img alt="PyPI version" src="https://img.shields.io/pypi/v/Reduino?logo=pypi" />
  </a>
  <a href="https://pypistats.org/packages/reduino">
    <img alt="PyPI downloads" src="https://img.shields.io/pypi/dm/Reduino?label=PyPI%20downloads&logo=pypi" />
  </a>
</div>

---

## Table of contents

* [Overview](#overview)
* [Quick start](#quick-start)
* [How it works](#how-it-works)
* [API reference](#api-reference)

  * [`Reduino.Actuators.Led`](#reduinoactuatorsled)
  * [`Reduino.Time.Sleep`](#reduinotimesleep)
  * [`Reduino.target`](#reduinotarget)
* [Supported devices & primitives](#supported-devices--primitives)
* [Supported Python features](#supported-python-features)
* [Testing](#testing)
* [Contributing](#contributing)
* [License](#license)

## Overview

Reduino lets you write a small, Pythonic DSL that transpiles to clean Arduino C++ and optionally flashes your board via PlatformIO. You get readable Python during development and reliable C++ on the device.

## Quick start

> **Requirements**: Python 3.10+, [PlatformIO](https://platformio.org/) for building/flashing.

```bash
pip install Reduino
pip install platformio  # required for uploads
```

If `upload=True`, Reduino will run `pio run -t upload` for you in a temporary PlatformIO project (Arduino Uno by default). You can re-run `pio run` later to rebuild or flash again.

## How it works

1. **Parse** – `Reduino.transpile.parser.parse()` builds an intermediate representation (IR) from your script.
2. **Analyze** – Constant folding, control-flow preservation, and safety checks happen on the IR.
3. **Emit** – `Reduino.transpile.emitter.emit()` produces Arduino-ready C++ (`main.cpp`).
4. **Toolchain** – `Reduino.target()` writes a `platformio.ini` (serial port & board), and optionally calls PlatformIO to build/flash.

Hardware side effects only occur on the device after upload—host-side execution is side-effect free.

## API reference

### `Reduino.Actuators.Led`

| Member                                                           | Description                                                        |
| ---------------------------------------------------------------- | ------------------------------------------------------------------ |
| `Led(pin=13)`                                                    | Create a virtual LED bound to an Arduino pin.                      |
| `on()` / `off()`                                                 | Turn LED fully on/off.                                             |
| `toggle()`                                                       | Flip between on/off.                                               |
| `get_state()`                                                    | `True` if LED is currently on.                                     |
| `get_brightness()` / `set_brightness(v)`                         | PWM level (0–255) read/write. Raises `ValueError` if out of range. |
| `blink(duration_ms, times=1)`                                    | Blink helper with internal waits.                                  |
| `fade_in(step=5, delay_ms=10)` / `fade_out(step=5, delay_ms=10)` | Gradual brightness ramp.                                           |
| `flash_pattern(pattern, delay_ms=200)`                           | Iterate over `[0/1 or 0–255]` values.                              |

**Example**

```python
from Reduino.Actuators import Led
led = Led(5)
led.set_brightness(128)
led.blink(250, times=3)
```

### `Reduino.Time.Sleep`

| Member                         | Description                                                |
| ------------------------------ | ---------------------------------------------------------- |
| `Sleep(ms, sleep_func=None)`   | Delay helper; custom `sleep_func` is injectable for tests. |
| `.seconds`                     | Duration exposed in seconds.                               |
| `.wait()` or call the instance | Perform the delay.                                         |

**Example**

```python
from Reduino.Time import Sleep
Sleep(500).wait()  # or Sleep(500)()
```

### `Reduino.target`

| Member                      | Description                                                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `target(port, upload=True)` | Transpile the current module; return generated C++. If `upload` is true, also build & flash via PlatformIO. The last call wins if used multiple times at top level. |

**Example**

```python
from Reduino import target
cpp = target("/dev/ttyACM0", upload=False)
print(cpp)
```


## Supported Python features

**Control flow**

* `while True:` becomes the Arduino `loop()` body.
* `for` over `range(...)`, lists/tuples, or generator expressions.
* `if` / `elif` / `else`, ternaries, `break`/`continue`.

**Variables & assignment**

* Regular assignment, tuple unpacking, pythonic swap `a, b = b, a`.
* Augmented ops (`+=`, `-=`, ...). Branch-local vars are promoted safely.

**Collections & comprehensions**

* Lists/tuples/dicts, membership tests, list methods (`append`, `extend`, ...).
* List comps & generators (evaluated eagerly into temps for safety).

**Functions & expressions**

* `def`/`return`, defaults, lambdas (on supported expressions).
* Literals: int/float/str/bool; casts: `int/float/bool/str`.
* Built-ins: `len`, `abs`, `max`, `min`, `sum`, `range`.

**Device primitives**

* LED pin init creates `pinMode`; actions become `digitalWrite`/PWM; sleeps become `delay(ms)`.

**Target directive**

* `target("PORT")` can appear anywhere at top level; the last call wins and is written to `platformio.ini`.

## Testing

```bash
pip install pytest
pytest
```

The suite covers parsing, emission, runtime helpers, and public primitives.

## Contributing

PRs for new actuators/sensors and transpiler improvements are welcome. See **CONTRIBUTING.md** for guidelines and the IR/emitter architecture.

## License

Reduino is distributed under **GPL-3.0**.

You may:

* Use, modify, and distribute under GPL-3.0.
* Build upon it in your open-source projects (derivatives must also be GPL-3.0).

For **closed-source** or **commercial** use, dual/custom licensing is available.

**Commercial inquiries:** [arnavbajaj9@gmail.com](mailto:arnavbajaj9@gmail.com)

---

© 2025 Arnav Bajaj. All rights reserved.
