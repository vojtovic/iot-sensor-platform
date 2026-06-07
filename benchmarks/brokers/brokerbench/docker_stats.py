"""Měření CPU/RAM kontejneru brokeru přes cgroup v2 (spolehlivější než `docker stats`).

`docker stats --no-stream` počítá CPU jako deltu mezi dvěma čteními a u lehkých
kontejnerů (Mosquitto, NanoMQ) opakovaně vracel 0.00 % — artefakt, ne realita
(ruční ověření ukázalo ~1,5 jádra pod zátěží). Proto čteme přímo cgroup:

- CPU: `cpu.stat` → `usage_usec` na začátku a konci kroku → využití jádra v %,
- RAM: `memory.current` vzorkovaná během kroku (gauge → avg + max).

CPU % je vztažené k JEDNOMU jádru (může přesáhnout 100 % na více jádrech),
stejná sémantika jako u `docker stats`.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from typing import Any


async def _docker_read(container: str, path: str) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", container, "cat", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out.decode() if proc.returncode == 0 else None
    except Exception:
        return None


async def _cpu_usage_usec(container: str) -> int | None:
    txt = await _docker_read(container, "/sys/fs/cgroup/cpu.stat")
    if not txt:
        return None
    for line in txt.splitlines():
        if line.startswith("usage_usec"):
            return int(line.split()[1])
    return None


async def _mem_bytes(container: str) -> int | None:
    """Working set = memory.current − inactive_file (reclaimovatelná cache pryč).

    Odpovídá tomu, co počítá `docker stats`; zahrnuje proces (anon) i kernel slab.
    """
    cur_txt = await _docker_read(container, "/sys/fs/cgroup/memory.current")
    if not cur_txt:
        return None
    try:
        current = int(cur_txt.strip())
    except ValueError:
        return None
    inactive_file = 0
    stat_txt = await _docker_read(container, "/sys/fs/cgroup/memory.stat")
    if stat_txt:
        for line in stat_txt.splitlines():
            if line.startswith("inactive_file "):
                inactive_file = int(line.split()[1])
                break
    return max(0, current - inactive_file)


async def sample_during(container: str, coro: Coroutine[Any, Any, Any]):
    """Spustí `coro` a změří CPU (cgroup delta přes celý krok) + RAM (vzorky).

    Vrátí (výsledek_coro, metrics), kde metrics = {cpu_pct, mem_mb_avg, mem_mb_max}.
    """
    t0 = time.monotonic()
    cpu0 = await _cpu_usage_usec(container)

    mem_samples: list[int] = []
    stop = asyncio.Event()

    async def mem_loop() -> None:
        while not stop.is_set():
            m = await _mem_bytes(container)
            if m is not None:
                mem_samples.append(m)
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(mem_loop())
    try:
        result = await coro
    finally:
        stop.set()
        await task

    t1 = time.monotonic()
    cpu1 = await _cpu_usage_usec(container)

    cpu_pct = 0.0
    if cpu0 is not None and cpu1 is not None and t1 > t0:
        cpu_pct = (cpu1 - cpu0) / ((t1 - t0) * 1_000_000) * 100.0

    metrics = {
        "cpu_pct": cpu_pct,
        "mem_mb_avg": (sum(mem_samples) / len(mem_samples) / 1_048_576) if mem_samples else 0.0,
        "mem_mb_max": (max(mem_samples) / 1_048_576) if mem_samples else 0.0,
    }
    return result, metrics
