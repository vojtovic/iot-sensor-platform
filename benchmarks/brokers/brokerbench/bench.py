"""Async jádro benchmarku — jeden krok rampy.

Architektura: subscriber a publisheři běží v ODDĚLENÝCH procesech (multiprocessing).
Kdyby běželi v jedné asyncio smyčce, publisheři by ji zahltili a subscriber by
nestíhal odbavovat → umělý strop daný klientem, ne brokerem. Oddělené procesy
mají vlastní smyčku i jádro (obchází GIL).

Publisher i subscriber měří čas přes time.time_ns na stejném hostu (různé procesy,
ale jedny systémové hodiny) → latence bez problému s rozsynchronizací.
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
import time
from dataclasses import dataclass, field

import aiomqtt

from .payload import make_payload, read_t_ns
from .stats import latency_summary


@dataclass
class StepResult:
    target_rate: int
    duration_s: float
    sent: int
    received: int
    throughput: float
    loss_pct: float
    lat: dict[str, float] = field(default_factory=dict)
    cpu_pct_avg: float = 0.0
    cpu_pct_max: float = 0.0
    mem_mb_avg: float = 0.0
    mem_mb_max: float = 0.0


# ── Subscriber proces ────────────────────────────────────────────────────

def _subscriber_proc(host: str, port: int, ready, stop, result_q, sample_every: int) -> None:
    async def run() -> None:
        received = 0
        lat: list[float] = []
        async with aiomqtt.Client(host, port=port, identifier="bench-sub") as client:
            await client.subscribe("bench/#", qos=1)
            ready.set()
            it = client.messages.__aiter__()
            while True:
                try:
                    msg = await asyncio.wait_for(it.__anext__(), timeout=0.5)
                except asyncio.TimeoutError:
                    if stop.is_set():
                        break
                    continue
                except StopAsyncIteration:
                    break
                received += 1
                if received % sample_every == 0:
                    t_ns = read_t_ns(msg.payload)
                    if t_ns is not None:
                        lat.append((time.time_ns() - t_ns) / 1e6)
                if stop.is_set():
                    # doodbavej co je hned k dispozici, pak konec
                    pass
        result_q.put((received, lat))

    asyncio.run(run())


# ── Publisher proces (obsluhuje skupinu klientů) ─────────────────────────

def _publisher_proc(host: str, port: int, client_ids: list[int],
                    rate_per_client: float, duration_s: float, qos: int, sent_q) -> None:
    async def one_client(idx: int) -> int:
        interval = 1.0 / rate_per_client if rate_per_client > 0 else 0.0
        topic = f"bench/dev{idx:03d}"
        device_id = f"bench-{idx:03d}"
        seq = 0
        deadline = time.monotonic() + duration_s
        next_t = time.monotonic()
        async with aiomqtt.Client(host, port=port, identifier=f"bench-pub-{idx}") as client:
            while time.monotonic() < deadline:
                seq += 1
                await client.publish(topic, make_payload(device_id, seq), qos=qos)
                next_t += interval
                sleep_for = next_t - time.monotonic()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
        return seq

    async def run() -> None:
        sent = await asyncio.gather(*(one_client(i) for i in client_ids))
        sent_q.put(sum(sent))

    asyncio.run(run())


async def run_step(host: str, port: int, target_rate: int, duration_s: float,
                   clients: int, qos: int, drain_s: float = 3.0,
                   sample_every: int = 1, pub_procs: int = 4) -> StepResult:
    """Spustí jeden krok rampy v oddělených procesech a vrátí naměřené hodnoty."""
    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    stop = ctx.Event()
    result_q = ctx.Queue()
    sent_q = ctx.Queue()

    sub = ctx.Process(target=_subscriber_proc,
                      args=(host, port, ready, stop, result_q, sample_every))
    sub.start()
    if not ready.wait(timeout=15):
        sub.terminate()
        raise RuntimeError("subscriber se nepřipojil včas")

    # rozděl klienty mezi publisher procesy
    rate_per_client = target_rate / clients
    groups: list[list[int]] = [[] for _ in range(pub_procs)]
    for i in range(clients):
        groups[i % pub_procs].append(i)

    pubs = [
        ctx.Process(target=_publisher_proc,
                    args=(host, port, g, rate_per_client, duration_s, qos, sent_q))
        for g in groups if g
    ]
    for p in pubs:
        p.start()
    for p in pubs:
        p.join()
    sent = sum(sent_q.get() for _ in pubs)

    await asyncio.sleep(drain_s)   # nech doputovat zprávy ve frontě
    stop.set()
    received, lat = result_q.get(timeout=10)
    sub.join(timeout=5)
    if sub.is_alive():
        sub.terminate()

    throughput = received / duration_s if duration_s > 0 else 0.0
    loss_pct = max(0.0, (sent - received) / sent * 100.0) if sent else 0.0
    return StepResult(
        target_rate=target_rate,
        duration_s=duration_s,
        sent=sent,
        received=received,
        throughput=throughput,
        loss_pct=loss_pct,
        lat=latency_summary(lat),
    )
