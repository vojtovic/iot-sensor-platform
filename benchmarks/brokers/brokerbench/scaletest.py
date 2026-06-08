"""Test škálovatelnosti počtu souběžných MQTT spojení.

Pro každý cílový počet N: otevře N souběžných spojení (a nechá je otevřená),
změří kolik se jich povedlo navázat, jak dlouho to trvalo a kolik RAM broker
přibral → paměť na jedno spojení. Cílí na nefunkční požadavek „škálovatelnost"
(stovky–tisíce jednotek).

Pozn.: každé spojení = 1 file descriptor; skript si zvedne soft limit (ulimit -n).
"""
from __future__ import annotations

import asyncio
import contextlib
import resource
import time
from dataclasses import dataclass

import aiomqtt
from paho.mqtt.client import MQTTv311

from .docker_stats import _mem_bytes


@dataclass
class ScaleResult:
    target: int
    connected: int
    failed: int
    connect_s: float
    conn_per_s: float
    mem_base_mb: float
    mem_after_mb: float
    mem_per_conn_kb: float


def _raise_fd_limit(needed: int) -> None:
    """Zvedne soft limit file descriptorů (kvůli mnoha spojením)."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    want = min(hard, needed + 256)
    if soft < want:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))


async def run_scale_step(host: str, port: int, n: int, container: str | None,
                         concurrency: int = 200) -> ScaleResult:
    _raise_fd_limit(n)
    stack = contextlib.AsyncExitStack()
    sem = asyncio.Semaphore(concurrency)
    connected = 0

    mem_base = (await _mem_bytes(container) or 0) / 1_048_576 if container else 0.0

    async def connect_one(i: int) -> None:
        nonlocal connected
        async with sem:
            try:
                c = aiomqtt.Client(host, port=port, identifier=f"scale-{i}",
                                   protocol=MQTTv311, timeout=15)
                await stack.enter_async_context(c)
                connected += 1
            except Exception:
                pass

    t0 = time.monotonic()
    await asyncio.gather(*(connect_one(i) for i in range(n)))
    connect_s = time.monotonic() - t0

    await asyncio.sleep(2)  # ať se RAM ustálí
    mem_after = (await _mem_bytes(container) or 0) / 1_048_576 if container else 0.0
    await stack.aclose()

    failed = n - connected
    per_conn_kb = ((mem_after - mem_base) * 1024 / connected) if connected else 0.0
    return ScaleResult(
        target=n,
        connected=connected,
        failed=failed,
        connect_s=connect_s,
        conn_per_s=connected / connect_s if connect_s > 0 else 0.0,
        mem_base_mb=mem_base,
        mem_after_mb=mem_after,
        mem_per_conn_kb=per_conn_kb,
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        prog="brokerbench.scaletest",
        description="Test škálovatelnosti počtu MQTT spojení",
    )
    ap.add_argument("--broker", default="broker")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--counts", default="500,2000,5000",
                    help="čárkou oddělené cílové počty spojení")
    ap.add_argument("--container", default=None, help="kontejner pro měření RAM")
    ap.add_argument("--concurrency", type=int, default=200)
    args = ap.parse_args()

    counts = [int(x) for x in args.counts.split(",") if x.strip()]
    print(f"Škálovatelnost spojení — {args.broker} ({args.host}:{args.port})")
    print("| spojení | navázáno | selhalo | čas s | conn/s | RAM MB | KB/spojení |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for n in counts:
        r = asyncio.run(run_scale_step(args.host, args.port, n,
                                       args.container, args.concurrency))
        print(f"| {r.target} | {r.connected} | {r.failed} | {r.connect_s:.1f} "
              f"| {r.conn_per_s:,.0f} | {r.mem_after_mb:.0f} | {r.mem_per_conn_kb:.1f} |")


if __name__ == "__main__":
    main()
