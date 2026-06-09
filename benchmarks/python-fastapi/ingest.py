"""Tenká ingestion služba (Python) — kandidát pro benchmark stacků (Fáze 3).

Kontrakt (stejný pro všechny stacky):
  MQTT subscribe → parse JSON → mapování kanálu → dávkový COPY do TimescaleDB.

- `time` sloupec = čas publikace z payloadu (`t_ns`), `received_at` = now() při
  insertu → latence (received_at − time) se měří DOTAZEM do DB (nezávisle na jazyku).
- Dávkování (BATCH_SIZE / FLUSH_MS) = stejná páka jako u ostatních stacků.
- Konfigurace přes proměnné prostředí.

Pozn.: kanály se načtou jednou při startu → harness musí zařízení nasít PŘED
spuštěním služby (bench-000…). Neznámé kanály se přeskočí (FK by je odmítl).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

import aiomqtt
import asyncpg

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "bench/#")
QOS = int(os.getenv("QOS", "1"))
DSN = os.getenv("DSN", "postgresql://iot:iot-dev@localhost:5432/iot")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "500"))
FLUSH_MS = float(os.getenv("FLUSH_MS", "100"))
INFLIGHT = int(os.getenv("INFLIGHT", "1000"))

COLUMNS = ["time", "device_id", "channel_id", "value", "quality", "seq"]


def parse(raw: bytes):
    """JSON → (device_id, seq, t_ns, [(quantity, value), …]) nebo None."""
    try:
        m = json.loads(raw)
        return (
            str(m["device_id"]),
            int(m["seq"]),
            int(m["t_ns"]),
            [(str(x["ch"]), float(x["v"])) for x in m.get("measurements", [])],
        )
    except (ValueError, KeyError, TypeError):
        return None


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    rows = await conn.fetch("SELECT id, device_id, quantity FROM channel")
    channel_map = {(r["device_id"], r["quantity"]): r["id"] for r in rows}

    batch: list[tuple] = []
    last_flush = time.monotonic()
    flush_s = FLUSH_MS / 1000.0

    async def flush() -> None:
        nonlocal batch, last_flush
        last_flush = time.monotonic()
        if not batch:
            return
        await conn.copy_records_to_table("telemetry", records=batch, columns=COLUMNS)
        batch = []

    async with aiomqtt.Client(
        MQTT_HOST, port=MQTT_PORT, identifier="py-ingest",
        max_inflight_messages=INFLIGHT, max_queued_incoming_messages=0,
    ) as client:
        await client.subscribe(MQTT_TOPIC, qos=QOS)
        print(f"[python] ingest: {MQTT_HOST}:{MQTT_PORT} topic={MQTT_TOPIC} "
              f"qos={QOS} batch={BATCH_SIZE}/{FLUSH_MS:.0f}ms channels={len(channel_map)}",
              flush=True)
        it = client.messages.__aiter__()
        while True:
            try:
                msg = await asyncio.wait_for(it.__anext__(), timeout=flush_s)
            except asyncio.TimeoutError:
                await flush()
                continue
            parsed = parse(msg.payload)
            if parsed is not None:
                dev, seq, t_ns, meas = parsed
                ts = datetime.fromtimestamp(t_ns / 1e9, tz=timezone.utc)
                for quantity, value in meas:
                    cid = channel_map.get((dev, quantity))
                    if cid is not None:
                        batch.append((ts, dev, cid, value, 0, seq))
            if len(batch) >= BATCH_SIZE or (time.monotonic() - last_flush) >= flush_s:
                await flush()


if __name__ == "__main__":
    asyncio.run(main())
