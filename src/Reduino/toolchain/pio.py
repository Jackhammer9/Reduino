from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable, List

SUPPORTED_ATMELAVR_BOARDS = frozenset(
    """
    1284p16m
    1284p8m
    168pa16m
    168pa8m
    328p16m
    328p8m
    32u416m
    644pa16m
    644pa8m
    AT90CAN128
    AT90CAN32
    AT90CAN64
    ATmega128
    ATmega1280
    ATmega1281
    ATmega1284
    ATmega1284P
    ATmega16
    ATmega162
    ATmega164A
    ATmega164P
    ATmega165
    ATmega165P
    ATmega168
    ATmega168P
    ATmega168PB
    ATmega169A
    ATmega169P
    ATmega2560
    ATmega2561
    ATmega32
    ATmega324A
    ATmega324P
    ATmega324PA
    ATmega324PB
    ATmega325
    ATmega3250
    ATmega3250P
    ATmega325P
    ATmega328
    ATmega328P
    ATmega328PB
    ATmega329
    ATmega3290
    ATmega3290P
    ATmega329P
    ATmega48
    ATmega48P
    ATmega48PB
    ATmega64
    ATmega640
    ATmega644A
    ATmega644P
    ATmega645
    ATmega6450
    ATmega6450P
    ATmega645P
    ATmega649
    ATmega6490
    ATmega6490P
    ATmega649P
    ATmega8
    ATmega8515
    ATmega8535
    ATmega88
    ATmega88P
    ATmega88PB
    LilyPadUSB
    a-star32U4
    alorium_hinj
    alorium_sno
    alorium_xlr8
    altair
    ardhat
    arduboy
    arduboy_devkit
    at90pwm216
    at90pwm316
    atmegangatmega168
    atmegangatmega8
    attiny13
    attiny13a
    attiny1634
    attiny167
    attiny2313
    attiny24
    attiny25
    attiny261
    attiny43
    attiny4313
    attiny44
    attiny441
    attiny45
    attiny461
    attiny48
    attiny828
    attiny84
    attiny841
    attiny85
    attiny861
    attiny87
    attiny88
    blend
    blendmicro16
    blendmicro8
    bluefruitmicro
    bob3
    btatmega168
    btatmega328
    chiwawa
    circuitplay_classic
    controllino_maxi
    controllino_maxi_automation
    controllino_mega
    controllino_mini
    diecimilaatmega168
    diecimilaatmega328
    digispark-pro
    digispark-pro32
    digispark-pro64
    digispark-tiny
    dwenguino
    elektor_uno_r4
    emonpi
    engduinov3
    esplora
    ethernet
    feather328p
    feather32u4
    fio
    flora8
    ftduino
    fysetc_f6_13
    gemma
    itsybitsy32u4_3V
    itsybitsy32u4_5V
    leonardo
    leonardoeth
    lightblue-bean
    lightblue-beanplus
    lightup
    lilypadatmega168
    lilypadatmega328
    lora32u4II
    mayfly
    megaADK
    megaatmega1280
    megaatmega2560
    metro
    micro
    mightyhat
    miniatmega168
    miniatmega328
    miniwireless
    moteino
    moteino8mhz
    moteinomega
    nanoatmega168
    nanoatmega328
    nanoatmega328new
    nibo2
    nibobee
    nibobee_1284
    niboburger
    niboburger_1284
    one
    panStampAVR
    pinoccio
    pro16MHzatmega168
    pro16MHzatmega328
    pro8MHzatmega168
    pro8MHzatmega328
    protrinket3
    protrinket3ftdi
    protrinket5
    protrinket5ftdi
    prusa_mm_control
    prusa_rambo
    quirkbot
    raspduino
    reprap_rambo
    robotControl
    robotMotor
    sanguino_atmega1284_8m
    sanguino_atmega1284p
    sanguino_atmega644
    sanguino_atmega644_8m
    sanguino_atmega644p
    sanguino_atmega644p_8m
    seeeduino
    sleepypi
    smart7688
    sodaq_galora
    sodaq_mbili
    sodaq_moja
    sodaq_ndogo
    sodaq_tatu
    sparkfun_digitalsandbox
    sparkfun_fiov3
    sparkfun_makeymakey
    sparkfun_megamini
    sparkfun_megapro16MHz
    sparkfun_megapro8MHz
    sparkfun_promicro16
    sparkfun_promicro8
    sparkfun_qduinomini
    sparkfun_redboard
    sparkfun_satmega128rfa1
    sparkfun_serial7seg
    the_things_uno
    tinyduino
    tinylily
    trinket3
    trinket5
    uno
    uno_mini
    usbasp
    uview
    whispernode
    wildfirev2
    wildfirev3
    yun
    yunmini
    zumbt328
    """.split()
)

SUPPORTED_ATMELMEGAAVR_BOARDS = frozenset(
    """
    ATmega1608
    ATmega1609
    ATmega3208
    ATmega3209
    ATmega4808
    ATmega4809
    ATmega808
    ATmega809
    ATtiny1604
    ATtiny1606
    ATtiny1607
    ATtiny1614
    ATtiny1616
    ATtiny1617
    ATtiny1624
    ATtiny1626
    ATtiny1627
    ATtiny202
    ATtiny204
    ATtiny212
    ATtiny214
    ATtiny3216
    ATtiny3217
    ATtiny3224
    ATtiny3226
    ATtiny3227
    ATtiny402
    ATtiny404
    ATtiny406
    ATtiny412
    ATtiny414
    ATtiny416
    ATtiny417
    ATtiny424
    ATtiny426
    ATtiny427
    ATtiny804
    ATtiny806
    ATtiny807
    ATtiny814
    ATtiny816
    ATtiny817
    ATtiny824
    ATtiny826
    ATtiny827
    AVR128DA28
    AVR128DA32
    AVR128DA48
    AVR128DA64
    AVR128DB28
    AVR128DB32
    AVR128DB48
    AVR128DB64
    AVR32DA28
    AVR32DA32
    AVR32DA48
    AVR32DB28
    AVR32DB32
    AVR32DB48
    AVR64DA28
    AVR64DA32
    AVR64DA48
    AVR64DA64
    AVR64DB28
    AVR64DB32
    AVR64DB48
    AVR64DB64
    AVR64DD14
    AVR64DD20
    AVR64DD28
    AVR64DD32
    avr_iot_wg
    curiosity_nano_4809
    curiosity_nano_da
    curiosity_nano_db
    nano_every
    uno_wifi_rev2
    xplained_nano_416
    xplained_pro_4809
    """.split()
)

SUPPORTED_PLATFORMS: dict[str, set[str]] = {
    "atmelavr": SUPPORTED_ATMELAVR_BOARDS,
    "atmelmegaavr": SUPPORTED_ATMELMEGAAVR_BOARDS,
}

BOARD_TO_PLATFORM = {
    board: platform
    for platform, boards in SUPPORTED_PLATFORMS.items()
    for board in boards
}


PIO_INI = """[env:{env_name}]
platform = {platform}
board = {board}
framework = arduino
upload_port = {port}

{lib_section}
"""


def _format_lib_section(libraries: Iterable[str] | None) -> str:
    """Render a ``lib_deps`` section for ``platformio.ini`` if needed."""

    if not libraries:
        return ""

    unique: List[str] = []
    for entry in libraries:
        if not entry:
            continue
        if entry not in unique:
            unique.append(entry)

    if not unique:
        return ""

    lines = ["lib_deps ="]
    lines.extend(f"  {name}" for name in unique)
    return "\n".join(lines)


def _sanitize_env_name(board: str) -> str:
    """Return a safe PlatformIO environment name based on ``board``."""

    return re.sub(r"[^A-Za-z0-9_]+", "_", board)


def validate_platform_board(platform: str, board: str) -> None:
    """Ensure the requested PlatformIO ``platform``/``board`` pair is supported."""

    if platform not in SUPPORTED_PLATFORMS:
        supported = ", ".join(sorted(SUPPORTED_PLATFORMS))
        raise ValueError(
            f"Unsupported PlatformIO platform '{platform}'. Supported platforms: {supported}."
        )

    if board not in BOARD_TO_PLATFORM:
        raise ValueError(
            f"Unsupported PlatformIO board '{board}'. Supported boards for the AVR platforms "
            "are listed at https://docs.platformio.org/en/latest/boards/index.html "
        )

    required_platform = BOARD_TO_PLATFORM[board]
    if required_platform != platform:
        raise ValueError(
            f"Board '{board}' requires PlatformIO platform '{required_platform}', not '{platform}'."
        )


def ensure_pio() -> None:
    try:
        subprocess.run(["pio", "--version"], check=True, stdout=subprocess.DEVNULL)
    except Exception as e:
        raise RuntimeError(
            "PlatformIO (pio) not found. Install with: pip install platformio"
        ) from e

def write_project(
    project_dir: Path,
    cpp_code: str,
    port: str,
    *,
    platform: str = "atmelavr",
    board: str = "uno",
    lib_deps: Iterable[str] | None = None,
) -> None:
    validate_platform_board(platform, board)
    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "main.cpp").write_text(cpp_code, encoding="utf-8")
    lib_section = _format_lib_section(lib_deps)
    env_name = _sanitize_env_name(board)
    ini_contents = (
        PIO_INI.format(
            env_name=env_name,
            platform=platform,
            board=board,
            port=port,
            lib_section=lib_section,
        ).rstrip()
        + "\n"
    )
    (project_dir / "platformio.ini").write_text(ini_contents, encoding="utf-8")

def compile_upload(project_dir: str | Path) -> None:
    project_dir = Path(project_dir)
    # First run triggers toolchain download automatically
    subprocess.run(["pio", "run"], cwd=project_dir, check=True)
    subprocess.run(["pio", "run", "-t", "upload"], cwd=project_dir, check=True)
