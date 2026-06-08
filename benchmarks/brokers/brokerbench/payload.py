"""Payload pro benchmark — realistická telemetrie + razítko času s vysokým rozlišením.

Do zprávy se vkládá `t_ns` (time.time_ns) odesílatele. Publisher i subscriber
běží ve stejném procesu (stejné hodiny), takže latence = now_ns - t_ns bez
problému s rozsynchronizovanými hodinami (riziko z TESTING.md odpadá).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

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


# ── Parsování pro ingestion do DB (pipeline benchmark) ───────────────────────
# Čisté funkce bez závislostí (json/datetime) → testovatelné bez brokeru i DB.

def parse_message(
    raw: bytes,
) -> tuple[str, int, int, list[tuple[str, float]]] | None:
    """JSON payload → (device_id, seq, t_ns, [(quantity, value), …]) nebo None.

    Pro ingestion do DB: vytáhne identitu, sekvenci, razítko a měření.
    """
    try:
        m = json.loads(raw)
        device_id = str(m["device_id"])
        seq = int(m["seq"])
        t_ns = int(m["t_ns"])
        meas = [(str(x["ch"]), float(x["v"])) for x in m.get("measurements", [])]
    except (ValueError, KeyError, TypeError):
        return None
    return device_id, seq, t_ns, meas


def rows_from_message(
    parsed: tuple[str, int, int, list[tuple[str, float]]],
    channel_map: dict[tuple[str, str], int],
) -> list[tuple[datetime, str, int, float, int, int]]:
    """(device_id, seq, t_ns, meas) → řádky `telemetry` pro COPY.

    Každé měření → jeden řádek (time, device_id, channel_id, value, quality, seq).
    `channel_map`: {(device_id, quantity): channel_id}. Měření bez známého kanálu
    se přeskočí (cizí/neregistrovaný kanál → backend by ho jinak odmítl na FK).
    """
    device_id, seq, t_ns, meas = parsed
    ts = datetime.fromtimestamp(t_ns / 1e9, tz=timezone.utc)
    rows: list[tuple[datetime, str, int, float, int, int]] = []
    for quantity, value in meas:
        cid = channel_map.get((device_id, quantity))
        if cid is not None:
            rows.append((ts, device_id, cid, value, 0, seq))
    return rows
