"""Placeholder runtime helper for the passive buzzer DSL primitive.

The runtime intentionally performs no action—the transpiler replaces calls to
this helper with Arduino code—but providing a small amount of documentation
helps users understand the surface area that *is* recognised during
transpilation.

Supported built-in melodies
===========================

The :meth:`Buzzer.melody` helper accepts the following melody names, mirroring
the emitter's bundled patterns.  Each name is case-sensitive.

``"success"``
    A quick, rising triad cue suitable for acknowledgement tones.
``"error"``
    A short descending blip that resolves to a low hold.
``"startup"``
    A C–E–G–C arpeggio, ideal for power-on or reset notifications.
``"notify"``
    A short double ping to highlight lightweight notifications.
``"alarm"``
    Alternating high/low notes that repeat eight times for urgency.
``"scale_c"``
    An ascending C-major scale resolving to the upper tonic.
``"siren"``
    A repeating two-note pattern that evokes a classic siren sweep.
"""

from __future__ import annotations


class Buzzer:
    """Lightweight stand-in so user code can instantiate :class:`Buzzer`.

    The transpiler recognises method calls on this placeholder and emits the
    corresponding Arduino implementation.  The methods themselves do not carry
    out any behaviour when executed on the host.
    """

    def __init__(self, pin: int = 8, *, default_frequency: float = 440.0) -> None:
        self.pin = pin
        self.default_frequency = default_frequency

    # The following helpers intentionally do nothing.  They exist purely so that
    # user code remains runnable prior to transpilation.
    def play_tone(
        self,
        frequency: float | int | str,
        duration_ms: float | int | str | None = None,
    ) -> None:  # pragma: no cover - placeholder
        return None

    def stop(self) -> None:  # pragma: no cover - placeholder
        return None

    def beep(
        self,
        frequency: float | int | str | None = None,
        *,
        on_ms: float | int | str = 100,
        off_ms: float | int | str = 100,
        times: int | str = 1,
    ) -> None:  # pragma: no cover - placeholder
        return None

    def sweep(
        self,
        start_hz: float | int | str,
        end_hz: float | int | str,
        *,
        duration_ms: float | int | str,
        steps: int | str = 10,
    ) -> None:  # pragma: no cover - placeholder
        return None

    def melody(
        self,
        name: str,
        *,
        tempo: float | int | str | None = None,
    ) -> None:  # pragma: no cover - placeholder
        return None
