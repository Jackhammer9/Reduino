"""In-memory model of an I2C PWM driver (e.g. PCA9685)."""

from __future__ import annotations


class PWMDriver:
    """High-level abstraction of a multi-channel PWM driver.

    The helper mirrors an I2C PWM expander style API while remaining hardware
    agnostic for host-side tests. Duty values are represented using a
    ``0..resolution`` integer range and normalized channel levels use ``0..1``.
    """

    def __init__(
        self,
        i2c_addr: int = 0x40,
        *,
        frequency_hz: float = 50.0,
        channels: int = 16,
        resolution: int = 4095,
    ) -> None:
        if not isinstance(i2c_addr, int):
            raise TypeError("i2c_addr must be an integer")
        if not 0 <= i2c_addr <= 0x7F:
            raise ValueError("i2c_addr must be between 0x00 and 0x7F")
        if channels <= 0:
            raise ValueError("channels must be positive")
        if resolution <= 0:
            raise ValueError("resolution must be positive")

        self.i2c_addr = i2c_addr
        self.channels = int(channels)
        self.resolution = int(resolution)
        self._frequency_hz = 0.0
        self._duty = [0] * self.channels
        self.set_frequency(float(frequency_hz))

    def _validate_channel(self, channel: int) -> int:
        if not isinstance(channel, int):
            raise TypeError("channel must be an integer")
        if not 0 <= channel < self.channels:
            raise ValueError("channel out of range")
        return channel

    def set_frequency(self, frequency_hz: float) -> None:
        """Set the PWM update frequency in hertz."""

        try:
            value = float(frequency_hz)
        except (TypeError, ValueError) as exc:
            raise TypeError("frequency_hz must be a number") from exc
        if value <= 0:
            raise ValueError("frequency_hz must be positive")
        self._frequency_hz = value

    def get_frequency(self) -> float:
        """Return the configured PWM frequency in hertz."""

        return self._frequency_hz

    def set_duty(self, channel: int, value: int) -> None:
        """Set one channel duty cycle using ``0..resolution`` scale."""

        index = self._validate_channel(channel)
        if not isinstance(value, int):
            raise TypeError("duty value must be an integer")
        if not 0 <= value <= self.resolution:
            raise ValueError(f"duty value must be between 0 and {self.resolution}")
        self._duty[index] = int(value)

    def get_duty(self, channel: int) -> int:
        """Return the duty value for ``channel``."""

        return self._duty[self._validate_channel(channel)]

    def set_level(self, channel: int, value: float) -> None:
        """Set a channel using a normalized level in the ``0..1`` range."""

        try:
            level = float(value)
        except (TypeError, ValueError) as exc:
            raise TypeError("level must be a number") from exc
        if not 0.0 <= level <= 1.0:
            raise ValueError("level must be between 0.0 and 1.0")
        duty = int(round(level * self.resolution))
        self.set_duty(channel, duty)

    def get_level(self, channel: int) -> float:
        """Return a channel's normalized level in the ``0..1`` range."""

        return self.get_duty(channel) / float(self.resolution)

    def off(self, channel: int) -> None:
        """Set one channel fully off."""

        self.set_duty(channel, 0)

    def all_off(self) -> None:
        """Turn all channels off."""

        for channel in range(self.channels):
            self._duty[channel] = 0

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "PWMDriver("
            f"i2c_addr=0x{self.i2c_addr:02X}, "
            f"frequency_hz={self._frequency_hz:.2f}, "
            f"channels={self.channels}, "
            f"resolution={self.resolution}"
            ")"
        )
