"""Sestavení telemetrické zprávy dle ROADMAP §6 (protokol, schema v1).

Čistá logika bez vedlejších efektů — snadno testovatelná bez brokeru.
"""
from __future__ import annotations

import time
from collections.abc import Iterable

SCHEMA_VERSION = "v1"

# Kanonické jednotky (SenML / RFC 8428). Musí odpovídat jednotkám v
# infra/timescale/init/03_seed.sql, aby telemetrie seděla na kanály v DB.
CHANNEL_UNITS: dict[str, str] = {
    "co2": "ppm",
    "temp": "Cel",
    "rh": "%RH",
    "voc": "ppb",
    "pres": "hPa",
}


def telemetry_topic(device_id: str) -> str:
    """MQTT topic pro telemetrii daného zařízení (ROADMAP §6 taxonomie)."""
    return f"v1/dev/{device_id}/telemetry"


def build_telemetry(
    device_id: str,
    seq: int,
    measurements: Iterable[tuple[str, float]],
    ts: int | None = None,
    meta: dict | None = None,
) -> dict:
    """Sestaví telemetrickou zprávu (schema v1).

    Args:
        device_id: stabilní id zařízení (např. "esp32-sim-001").
        seq: monotónní čítač — řazení, deduplikace, detekce ztráty, replay.
        measurements: dvojice (kanál, hodnota), např. [("co2", 812.0)].
        ts: čas vzniku na zařízení (unix s). Default = teď.
        meta: volitelná metadata (fw, batt, …).
    """
    if ts is None:
        ts = int(time.time())
    msg: dict = {
        "schema": SCHEMA_VERSION,
        "device_id": device_id,
        "ts": ts,
        "seq": seq,
        "measurements": [
            {"ch": ch, "v": round(v, 2), "u": CHANNEL_UNITS[ch]}
            for ch, v in measurements
        ],
    }
    if meta:
        msg["meta"] = meta
    return msg
