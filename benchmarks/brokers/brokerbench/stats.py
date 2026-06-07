"""Čisté výpočetní funkce pro benchmark — percentily a parsování docker stats.

Bez vedlejších efektů → snadno testovatelné.
"""
from __future__ import annotations

from collections.abc import Sequence


def percentile(sorted_values: Sequence[float], p: float) -> float:
    """p-tý percentil (0–100) ze SETŘÍDĚNÉ posloupnosti (lineární interpolace).

    Prázdná posloupnost → 0.0.
    """
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_values[0])
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def latency_summary(latencies_ms: Sequence[float]) -> dict[str, float]:
    """Souhrn latencí (ms): p50, p95, p99, max, avg."""
    if not latencies_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "avg": 0.0}
    s = sorted(latencies_ms)
    return {
        "p50": percentile(s, 50),
        "p95": percentile(s, 95),
        "p99": percentile(s, 99),
        "max": float(s[-1]),
        "avg": sum(s) / len(s),
    }


# Převod jednotek velikosti, jak je vypisuje docker stats (binární: KiB/MiB/GiB).
_MEM_UNITS = {
    "B": 1 / (1024 * 1024),
    "KIB": 1 / 1024,
    "MIB": 1.0,
    "GIB": 1024.0,
    # docker občas použije i dekadické značky
    "KB": 1 / 1024,
    "MB": 1.0,
    "GB": 1024.0,
}


def parse_mem_mb(mem_token: str) -> float:
    """'45.6MiB' → 45.6 (v MB). '1.2GiB' → 1228.8."""
    token = mem_token.strip()
    num = ""
    unit = ""
    for ch in token:
        if ch.isdigit() or ch == ".":
            num += ch
        else:
            unit += ch
    if not num:
        return 0.0
    factor = _MEM_UNITS.get(unit.strip().upper(), 1.0)
    return float(num) * factor


def parse_docker_stats(line: str) -> dict[str, float] | None:
    """Naparsuje řádek `docker stats --no-stream --format '{{.CPUPerc}}|{{.MemUsage}}'`.

    Příklad vstupu: '12.34%|45.6MiB / 7.5GiB' → {'cpu_pct': 12.34, 'mem_mb': 45.6}.
    Vrátí None, pokud řádek nedává smysl.
    """
    line = line.strip()
    if "|" not in line:
        return None
    cpu_part, mem_part = line.split("|", 1)
    cpu_part = cpu_part.strip().rstrip("%").strip()
    try:
        cpu = float(cpu_part)
    except ValueError:
        return None
    mem_used = mem_part.split("/", 1)[0].strip()
    return {"cpu_pct": cpu, "mem_mb": parse_mem_mb(mem_used)}
