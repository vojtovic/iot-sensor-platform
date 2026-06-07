"""Payload pro benchmark — realistická telemetrie + razítko času s vysokým rozlišením.

Do zprávy se vkládá `t_ns` (time.time_ns) odesílatele. Publisher i subscriber
běží ve stejném procesu (stejné hodiny), takže latence = now_ns - t_ns bez
problému s rozsynchronizovanými hodinami (riziko z TESTING.md odpadá).
"""
from __future__ import annotations

import json
import time

# Realistický payload odpovídající telemetrii (ROADMAP §6), ~200 B.
_BASE = {
    "schema": "v1",
    "measurements": [
        {"ch": "co2", "v": 812.0, "u": "ppm"},
        {"ch": "temp", "v": 23.4, "u": "Cel"},
        {"ch": "rh", "v": 41.2, "u": "%RH"},
    ],
    "meta": {"fw": "1.0.0", "batt": 87},
}


def make_payload(device_id: str, seq: int, t_ns: int | None = None) -> bytes:
    """Sestaví benchmark zprávu s razítkem t_ns (pro měření latence)."""
    if t_ns is None:
        t_ns = time.time_ns()
    msg = dict(_BASE)
    msg["device_id"] = device_id
    msg["seq"] = seq
    msg["t_ns"] = t_ns
    return json.dumps(msg).encode()


def read_t_ns(raw: bytes) -> int | None:
    """Vytáhne t_ns z přijaté zprávy (None pokud chybí / nevalidní)."""
    try:
        return int(json.loads(raw)["t_ns"])
    except (ValueError, KeyError, TypeError):
        return None
