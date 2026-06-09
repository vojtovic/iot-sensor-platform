"""Benchmark kandidátských backend stacků (Fáze 3).

Měří EXTERNÍ ingestion službu (kontejner, libovolný jazyk) férově zvenčí:
  - zátěž generuje stejný publisher jako broker/pipeline benchmark,
  - propustnost a latence se čtou z TimescaleDB (latence = received_at − time,
    kde `time` = čas publikace z payloadu) → nezávislé na jazyku služby,
  - CPU/RAM = cgroup kontejneru služby (sample_during).

Předpoklad: služba (kontejner `--container`) už BĚŽÍ a je připojená k brokeru i DB;
zařízení bench-000… jsou nasít (řeší runner). Telemetrie se před každým krokem
vyprázdní (měří se jen daný krok).

Použití (obvykle přes run_stacks.sh):
    python -m brokerbench.stackbench --stack python --container iot-ingest-python \\
        --dsn postgresql://iot:iot-dev@localhost:5432/iot --rates 1000,5000,10000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing as mp
import time
from pathlib import Path

from .bench import StepResult, _publisher_proc, median_step
from .docker_stats import sample_during


def parse_rates(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip()]


async def _connect(dsn: str):
    import asyncpg
    return await asyncpg.connect(dsn)


async def reset_telemetry(dsn: str) -> None:
    conn = await _connect(dsn)
    try:
        await conn.execute("TRUNCATE telemetry")
    finally:
        await conn.close()


async def db_metrics(dsn: str, duration_s: float) -> tuple[int, dict[str, float]]:
    """Z telemetrie (vyprázdněné před krokem) spočítá uložené zprávy + latenci.

    Vrátí (uložených_zpráv, {p50,p95,p99,max,avg}). 1 zpráva = 3 řádky (měření).
    Latence = received_at − time (ms).
    """
    conn = await _connect(dsn)
    try:
        rows = await conn.fetchval("SELECT count(*) FROM telemetry")
        lat = await conn.fetchrow(
            "SELECT "
            " percentile_cont(0.50) WITHIN GROUP (ORDER BY l) AS p50,"
            " percentile_cont(0.95) WITHIN GROUP (ORDER BY l) AS p95,"
            " percentile_cont(0.99) WITHIN GROUP (ORDER BY l) AS p99,"
            " max(l) AS mx, avg(l) AS av "
            "FROM (SELECT EXTRACT(EPOCH FROM (received_at - time))*1000 AS l "
            "      FROM telemetry) t"
        )
    finally:
        await conn.close()
    msgs = (rows or 0) // 3
    summary = {
        "p50": float(lat["p50"] or 0), "p95": float(lat["p95"] or 0),
        "p99": float(lat["p99"] or 0), "max": float(lat["mx"] or 0),
        "avg": float(lat["av"] or 0),
    }
    return msgs, summary


async def _drive(host: str, port: int, target_rate: int, duration_s: float,
                 clients: int, qos: int, drain_s: float, pub_procs: int = 4) -> int:
    """Pustí publishery (stejné jako broker/pipeline) a vrátí počet odeslaných zpráv."""
    ctx = mp.get_context("spawn")
    sent_q = ctx.Queue()
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
    await asyncio.sleep(drain_s)   # nech službu doinsertovat zbytek dávky
    return sent


async def run_stack_step(host: str, port: int, dsn: str, container: str,
                         target_rate: int, duration_s: float, clients: int, qos: int,
                         drain_s: float = 5.0) -> StepResult:
    await reset_telemetry(dsn)
    sent, metrics = await sample_during(
        container, _drive(host, port, target_rate, duration_s, clients, qos, drain_s)
    )
    stored, lat = await db_metrics(dsn, duration_s)
    throughput = stored / duration_s if duration_s > 0 else 0.0
    loss_pct = max(0.0, (sent - stored) / sent * 100.0) if sent else 0.0
    return StepResult(
        target_rate=target_rate, duration_s=duration_s,
        sent=sent, received=stored, throughput=throughput, loss_pct=loss_pct,
        lat=lat,
        ing_cpu_pct=metrics["cpu_pct"], ing_mem_mb=metrics["mem_mb_max"],
    )


async def run_ramp(args: argparse.Namespace) -> list[StepResult]:
    results: list[StepResult] = []
    if args.warmup:
        print("  zahřívací krok…", flush=True)
        await run_stack_step(args.host, args.port, args.dsn, args.container,
                             parse_rates(args.rates)[0], args.duration, args.clients,
                             args.qos, args.drain)
        await asyncio.sleep(1.0)
    for rate in parse_rates(args.rates):
        rep = max(1, args.repeat)
        print(f"  → krok: cíl {rate} zpráv/s × {rep}…", flush=True)
        runs = [await run_stack_step(args.host, args.port, args.dsn, args.container,
                                     rate, args.duration, args.clients, args.qos, args.drain)
                for _ in range(rep)]
        step = median_step(runs)
        results.append(step)
        print(f"    uloženo {step.throughput:,.0f}/s · p95 {step.lat['p95']:.1f} ms · "
              f"ztráta {step.loss_pct:.1f}% · CPU {step.ing_cpu_pct:.0f}% · "
              f"RAM {step.ing_mem_mb:.0f} MB", flush=True)
        await asyncio.sleep(1.0)
    return results


def print_table(stack: str, results: list[StepResult]) -> None:
    print(f"\n### {stack} — ingestion → TimescaleDB\n")
    print("| cíl/s | uloženo/s | ztráta % | p50 | p95 | p99 | max | CPU % | RAM MB |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        print(f"| {r.target_rate:,} | {r.throughput:,.0f} | {r.loss_pct:.1f} "
              f"| {r.lat['p50']:.1f} | {r.lat['p95']:.1f} | {r.lat['p99']:.1f} | {r.lat['max']:.1f} "
              f"| {r.ing_cpu_pct:.0f} | {r.ing_mem_mb:.0f} |")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brokerbench.stackbench",
                                description="Benchmark backend stacku (externí ingestion)")
    p.add_argument("--stack", default="stack", help="popisek (python/dotnet/node/java)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--dsn", default="postgresql://iot:iot-dev@localhost:5432/iot")
    p.add_argument("--container", required=True, help="běžící kontejner ingestion služby")
    p.add_argument("--rates", default="1000,2500,5000,7500,10000")
    p.add_argument("--duration", type=float, default=8.0)
    p.add_argument("--clients", type=int, default=20)
    p.add_argument("--qos", type=int, default=1, choices=[0, 1, 2])
    p.add_argument("--drain", type=float, default=5.0)
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--warmup", action="store_true")
    p.add_argument("--json", default=None)
    return p


def main() -> None:
    args = build_parser().parse_args()
    print(f"Stack benchmark '{args.stack}' (broker {args.host}:{args.port} → DB, "
          f"kontejner {args.container})")
    results = asyncio.run(run_ramp(args))
    print_table(args.stack, results)
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"broker": f"stack-{args.stack}", "stack": args.stack, "qos": args.qos,
             "clients": args.clients, "duration_s": args.duration, "mode": "stack",
             "steps": [vars(r) for r in results]}, indent=2))
        print(f"\nVýsledky uloženy do {out}")


if __name__ == "__main__":
    main()
