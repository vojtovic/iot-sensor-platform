"""CLI sensor simulátoru (Fáze 2).

Příklad:
    python -m simulator --devices 2 --rate 1 --duration 10
    python -m simulator --devices 100 --rate 5 --broker localhost:1883

Rozšíření (rampa, výpadek + replay, chybné zprávy) viz simulator/README.md
a TESTING.md §4 — přijdou ve fázích zátěžových a fault-injection testů.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import signal

import aiomqtt

from .device import SimulatedDevice


def device_id(i: int) -> str:
    """Stabilní id zařízení — pro 2 zařízení sedí na seed v DB (esp32-sim-001/002)."""
    return f"esp32-sim-{i:03d}"


def parse_broker(s: str) -> tuple[str, int]:
    """Akceptuje 'host:port', 'host' nebo 'mqtt://host:port'."""
    s = s.removeprefix("mqtt://")
    if ":" in s:
        host, port = s.rsplit(":", 1)
        return host, int(port)
    return s, 1883


async def run_device(
    client: aiomqtt.Client,
    dev: SimulatedDevice,
    rate: float,
    stop: asyncio.Event,
    count: int | None,
) -> int:
    """Publikuje telemetrii daného zařízení dokud nepřijde stop / nedojde count."""
    interval = 1.0 / rate
    sent = 0
    while not stop.is_set():
        payload = dev.next_payload()
        await client.publish(dev.topic, json.dumps(payload), qos=1)
        sent += 1
        if count is not None and sent >= count:
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    return sent


async def main_async(args: argparse.Namespace) -> None:
    seed_rng = random.Random(args.seed)
    devices = [
        # každé zařízení dostane vlastní deterministický RNG odvozený ze seedu
        SimulatedDevice(device_id(i + 1), random.Random(seed_rng.random()))
        for i in range(args.devices)
    ]

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    host, port = parse_broker(args.broker)
    print(
        f"Připojuji se k {host}:{port} | {args.devices} zařízení | "
        f"{args.rate} Hz | {'∞' if not args.duration else f'{args.duration}s'}"
    )

    async with aiomqtt.Client(hostname=host, port=port) as client:
        if args.duration:
            loop.call_later(args.duration, stop.set)
        tasks = [
            asyncio.create_task(run_device(client, d, args.rate, stop, args.count))
            for d in devices
        ]
        results = await asyncio.gather(*tasks)

    total = sum(results)
    print(f"Odesláno {total} zpráv ({len(devices)} zařízení).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="simulator", description="Sensor simulator (Fáze 2)")
    p.add_argument("--devices", type=int, default=2, help="počet virtuálních zařízení")
    p.add_argument("--broker", default="localhost:1883", help="host:port MQTT brokeru")
    p.add_argument("--rate", type=float, default=1.0, help="zpráv za sekundu na zařízení")
    p.add_argument("--duration", type=float, default=None, help="délka běhu v s (jinak do Ctrl+C)")
    p.add_argument("--count", type=int, default=None, help="max zpráv na zařízení")
    p.add_argument("--seed", type=int, default=None, help="seed RNG pro opakovatelné běhy")
    return p


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
