"""Model jednoho simulovaného zařízení.

Každé zařízení má vlastní `device_id`, `seq` čítač a sadu kanálů, jejichž
hodnoty se vyvíjejí náhodnou procházkou v realistickém rozsahu.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .payload import build_telemetry, telemetry_topic


@dataclass
class ChannelModel:
    """Kanál s hodnotou vyvíjenou náhodnou procházkou v mezích [lo, hi]."""

    quantity: str
    value: float
    lo: float
    hi: float
    step: float

    def tick(self, rng: random.Random) -> float:
        self.value += rng.uniform(-self.step, self.step)
        self.value = max(self.lo, min(self.hi, self.value))
        return self.value


def default_channels(rng: random.Random) -> list[ChannelModel]:
    """Výchozí trojice kanálů co2 / temp / rh (odpovídá seedu v DB)."""
    return [
        ChannelModel("co2", rng.uniform(450, 700), 400, 2000, 25),
        ChannelModel("temp", rng.uniform(20, 24), 15, 30, 0.3),
        ChannelModel("rh", rng.uniform(35, 50), 20, 70, 1.0),
    ]


@dataclass
class SimulatedDevice:
    device_id: str
    rng: random.Random
    fw: str = "1.0.0"
    seq: int = 0
    channels: list[ChannelModel] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.channels:
            self.channels = default_channels(self.rng)

    @property
    def topic(self) -> str:
        return telemetry_topic(self.device_id)

    def next_payload(self, ts: int | None = None) -> dict:
        """Posune `seq`, vyvine kanály a vrátí novou telemetrickou zprávu."""
        self.seq += 1
        measurements = [(c.quantity, c.tick(self.rng)) for c in self.channels]
        meta = {"fw": self.fw, "batt": self.rng.randint(80, 100)}
        return build_telemetry(self.device_id, self.seq, measurements, ts=ts, meta=meta)
