<div align="center">
  <img src="https://raw.githubusercontent.com/Jackhammer9/Reduino/refs/heads/main/.github/workflows/Reduino.png" alt="Reduino" width="360" />

  <h1>Reduino</h1>
  <p><em>Write friendly Python. Get Arduino-ready C++. Upload Easily to MCUs.</em></p>

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
* [The `target()` function (Required)](#the-target-function-required)
* [API reference](#api-reference)
  * [Actuators](#actuators)
    * [LED](#led)
    * [RGB LED](#rgb-led)
    * [Buzzer](#buzzer)
    * [Servo](#servo)
  * [Sensors](#sensors)
    * [Button](#button)
    * [Potentiometer](#potentiometer)
    * [Ultrasonic](#ultrasonic)
  * [Communication](#communication)
    * [SerialMonitor](#serialmonitor)
  * [Utilities](#utilities)
    * [sleep](#sleep)
    * [map](#map)
* [Supported Python features](#supported-python-features)
* [License](#license)

---

## Overview

**Reduino** lets you write high-level Python that compiles into clean Arduino C++, then optionally uploads it to your board via PlatformIO.

---

## Quick start

```bash
pip install Reduino
pip install platformio  # required for automatic uploads
```

> [!NOTE]
> PlatformIO is only required for **automatic** build & upload. You can still transpile without it.

---

## The `target()` function (Required)

Place `target()` **at the very top of your script**, immediately after imports. This is the entry point that tells Reduino to parse your entire file, transpile it to Arduino C++, and (optionally) upload it.

| Parameter |  Type  | Default | Description                                                             |
| --------: | :----: | :-----: | ----------------------------------------------------------------------- |
|    `port` |  `str` |    —    | Serial port, e.g. `"COM3"` or `"/dev/ttyACM0"`.                         |
|  `upload` | `bool` |  `True` | If `True`, compile & upload via PlatformIO. If `False`, only transpile. |

**Returns:** `str` of the generated Arduino C++ source.

**Minimal example (top-of-file `target`)**

```python
from Reduino import target
target("COM3")  # upload=True by default

# Your Reduino code below...
```

### Example: Reduino structure explained

Reduino automatically splits your Python code into Arduino sections.

```python
from Reduino import target
target("COM3")

from Reduino.Actuators import Led
led = Led(13)

while True:
    led.toggle()          # repeated code -> goes into void loop()
```
Generated Arduino structure (conceptually):

```cpp
void setup() {
  pinMode(13, OUTPUT);
}

void loop() {
  digitalWrite(13, !digitalRead(13));
  delay(500);
}
```
Everything before while True: (declarations, prints, sensor setup, etc.)
is placed inside setup(), and everything inside the while True loop is placed in loop().

**Transpile only (no upload)**

```python
from Reduino import target
cpp = target("COM3", upload=False)
print(cpp)

# Your Reduino code below...
```

> [!IMPORTANT]
> `target()` reads the whole file text and generates code for everything below it.
> If `upload=True`, it also builds and flashes using a temporary PlatformIO project.

---

## API reference

### Actuators

#### LED

| Method                                                           | Description                       |
| ---------------------------------------------------------------- | --------------------------------- |
| `Led(pin=13)`                                                    | Bind an LED to a digital/PWM pin. |
| `on()` / `off()`                                                 | Turn fully on/off.                |
| `toggle()`                                                       | Flip state.                       |
| `get_state()`                                                    | `True` if on.                     |
| `get_brightness()` / `set_brightness(v)`                         | PWM 0–255.                        |
| `blink(duration_ms, times=1)`                                    | Blink helper.                     |
| `fade_in(step=5, delay_ms=10)` / `fade_out(step=5, delay_ms=10)` | Smooth ramp.                      |
| `flash_pattern(pattern, delay_ms=200)`                           | Run pattern of 0 & 1s eg: `[1,0,0,1,1,1]`.  |

**Example**

```python
from Reduino import target
target("COM3")

from Reduino.Actuators import Led
from Reduino.Utils import sleep

led = Led(9)
led.set_brightness(128)
led.blink(200, times=3)
sleep(500)
led.off()
```

---

#### RGB LED

| Method                                  | Description                 |
| --------------------------------------- | --------------------------- |
| `RGBLed(r_pin, g_pin, b_pin)`           | Bind RGB to three PWM pins. |
| `set_color(r,g,b)`                      | Set color (0–255 each).     |
| `on(r=255,g=255,b=255)` / `off()`       | White / off.                |
| `fade(r,g,b,duration_ms=1000,steps=50)` | Transition to target color. |
| `blink(r,g,b,times=1,delay_ms=200)`     | Blink with color.           |

**Example**

```python
from Reduino import target
target("COM3")

from Reduino.Actuators import RGBLed
from Reduino.Utils import sleep

rgb = RGBLed(9, 10, 11)
rgb.set_color(0, 128, 255)
rgb.fade(255, 0, 0, duration_ms=1500)
sleep(300)
rgb.off()
```

---

#### Buzzer

| Method                                                 | Description           |
| ------------------------------------------------------ | --------------------- |
| `Buzzer(pin=8, default_frequency=440.0)`               | Create buzzer.        |
| `play_tone(frequency, duration_ms=None)`               | Play tone.            |
| `stop()`                                               | Stop sound.           |
| `beep(frequency=None, on_ms=100, off_ms=100, times=1)` | Repeated tone.        |
| `sweep(start_hz, end_hz, duration_ms, steps=10)`       | Sweep frequencies.    |
| `melody(name, tempo=None)`                             | Play built-in melody. |

**Built-in melodies**: `success`, `error`, `startup`, `notify`, `alarm`, `scale_c`, `siren`

**Example**

```python
from Reduino import target
target("COM3")

from Reduino.Actuators import Buzzer
from Reduino.Utils import sleep

bz = Buzzer(8)
bz.melody("startup")
sleep(500)
bz.beep(frequency=880, on_ms=100, off_ms=100, times=3)
bz.stop()
```

---

#### Servo

| Method                                                                          | Description                    |
| ------------------------------------------------------------------------------- | ------------------------------ |
| `Servo(pin=9, min_angle=0, max_angle=180, min_pulse_us=544, max_pulse_us=2400)` | Create servo.                  |
| `write(angle)`                                                                  | Move to degrees (clamped).     |
| `write_us(pulse)`                                                               | Move by pulse width (clamped). |

**Example**

```python
from Reduino import target
target("COM3")

from Reduino.Actuators import Servo
from Reduino.Utils import sleep

s = Servo(9)
s.write(90)
sleep(500)
s.write(0)
```

---

### Sensors

#### Button

| Method                                            | Description                                  |
| ------------------------------------------------- | -------------------------------------------- |
| `Button(pin, on_click=None, state_provider=None)` | Digital input w/ optional callback/provider. |
| `is_pressed()`                                    | `1` if pressed else `0`.                     |

**Example**

```python
from Reduino import target
from Reduino.Actuators import Led
from Reduino.Sensors import Button

target("COM3")

led = Led(6)
btn = Button(7)
if btn.is_pressed():
    led.toggle()
```

---

#### Potentiometer

| Method                                         | Description     |
| ---------------------------------------------- | --------------- |
| `Potentiometer(pin="A0", value_provider=None)` | Analog helper.  |
| `read()`                                       | 0–1023 integer. |

**Example**

```python
from Reduino import target
from Reduino.Communication import SerialMonitor
target("COM3")

from Reduino.Sensors import Potentiometer

mon = SerialMonitor(9600 , "COM3")
pot = Potentiometer("A0")

while True:
    value = pot.read()
    mon.write(value)
```

---

#### Ultrasonic

| Method                                                                                   | Description                                |
| ---------------------------------------------------------------------------------------- | ------------------------------------------ |
| `Ultrasonic(trig, echo, sensor="HC-SR04", distance_provider=None, default_distance=0.0)` | HC-SR04 factory.                           |
| `measure_distance()`                                                                     | Distance in cm (handles timeouts/backoff). |

**Example**

```python
from Reduino import target
target("COM3")

from Reduino.Sensors import Ultrasonic
from Reduino.Utils import sleep

u = Ultrasonic(trig=9, echo=10)
d = u.measure_distance()
print(d)
sleep(60)
```

---

### Communication

#### SerialMonitor

| Method                                                  | Description                        |
| ------------------------------------------------------- | ---------------------------------- |
| `SerialMonitor(baud_rate=9600, port=None, timeout=1.0)` | Host-side serial console.          |
| `connect(port)`                                         | Open serial (requires `pyserial`). |
| `close()`                                               | Close port.                        |
| `write(value)`                                          | Send text.                         |
| `read()`                                                | Read text.                         |

**Example (host-side)**

```python
from Reduino import target
target("COM3")

from Reduino.Communication import SerialMonitor

mon = SerialMonitor(baud_rate=115200, port="COM4")

while True:
    mon.write("hello")
    mon.read()
    mon.close()
```

> [!NOTE]
> `pyserial` is optional; only needed if you call `connect()`.

---

### Utilities

#### sleep

```python
from Reduino import target
target("COM3")

from Reduino.Utils import sleep
sleep(250)  # ms
```

#### map

```python
from Reduino import target
target("COM3")

from Reduino.Utils import map
mapped = map(512, 0, 1023, 0.0, 5.0)  # 2.5-ish
print(mapped)
```

---

## Supported Python features

Reduino implements a pragmatic subset of Python that cleanly lowers to Arduino C++.

### Control flow

* `while True:` ➜ Arduino `loop()`
* `for x in range(...)`, including `range(start, stop, step)`
* `if / elif / else`, `break`, `continue`, `try/except` (mapped to C++ try/catch where used)

### Variables & assignment

* Standard assignment and **pythonic swap**:

  ```python
  a, b = b, a
  ```
* Multiple assignment & tuple unpacking
* Augmented ops (`+=`, `-=`, `*=`, etc.)

### Collections

* **Lists** (`[]`), tuples (`()`), and membership checks (`x in items`)
* **List comprehensions**:

  ```python
  squares = [i for i in range(10)]
  ```
* `len()` on strings, lists, and internal list type

### Built-ins

* `len()`, `abs()`, `max()`, `min()`
* `print()` maps to serial printing in emitted code when serial is configured

> [!TIP]
> Many constant expressions are folded at transpile time for smaller, faster C++.

---

## License

Reduino is distributed under the **GNU General Public License v3.0 (GPLv3)**.  
You are free to use, modify, and distribute this software for personal or educational purposes,  
as long as derivative works remain open-source and licensed under the same terms.

For commercial usage, redistribution, or integration into closed-source systems,  
please contact me at arnavbajaj9@gmail.com for alternative licensing options.

See [LICENSE](https://www.gnu.org/licenses/gpl-3.0) for full details.
