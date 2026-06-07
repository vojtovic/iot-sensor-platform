"""Vzorkování CPU/RAM kontejneru brokeru přes `docker stats` během kroku.

`sample_during` pustí na pozadí periodické snímky `docker stats` po dobu, co
běží předaná korutina (jeden krok benchmarku), a vrátí (výsledek, vzorky).
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from .stats import parse_docker_stats


async def _sample_loop(container: str, samples: list[dict], stop: asyncio.Event,
                       interval: float = 1.0) -> None:
    while not stop.is_set():
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "stats", "--no-stream", "--format",
                "{{.CPUPerc}}|{{.MemUsage}}", container,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            for line in out.decode().splitlines():
                rec = parse_docker_stats(line)
                if rec:
                    samples.append(rec)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def sample_during(container: str, coro: Coroutine[Any, Any, Any]):
    """Spustí `coro` a paralelně vzorkuje docker stats kontejneru.

    Vrátí (výsledek_coro, list_vzorků), kde vzorek = {'cpu_pct', 'mem_mb'}.
    """
    samples: list[dict] = []
    stop = asyncio.Event()
    task = asyncio.create_task(_sample_loop(container, samples, stop))
    try:
        result = await coro
    finally:
        stop.set()
        await task
    return result, samples
