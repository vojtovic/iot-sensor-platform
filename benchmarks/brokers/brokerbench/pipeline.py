"""End-to-end benchmark: publisher → broker → ingestion → TimescaleDB.

Rozšiřuje broker-only benchmark (bench.py) o REÁLNÝ zápis do databáze. Měří, kolik
stojí ingestion + perzistence oproti samotnému brokeru:

- **latence** = publish → COMMIT v TimescaleDB (durable, ne jen „přijato"),
- **propustnost** = uložených zpráv/s (smysl má hlavně tam, kde je ztráta ≈ 0),
- **CPU/RAM DB** = kontejneru TimescaleDB,
- **CPU/RAM ingesteru** = procesu konzumenta (psutil) — bez toho je „systémová cena"
  podhodnocená (konzument může žrát víc než DB).

Konzument zapisuje DÁVKOVĚ (asyncpg COPY) — realistická ingestion vrstva
(ROADMAP §4). Latence se vztahuje k času COMMITU dávky, takže je z principu
ovlivněná `flush_ms` + durabilitou Postgresu (`synchronous_commit`) — proto se obojí
reportuje.

Publisher se sdílí s broker-only benchmarkem (`bench._publisher_proc`) → zátěž je
identická a srovnání férové. asyncpg/psutil se importují LÍNĚ, aby čisté funkce
v payload.py šly testovat bez nainstalované DB/měřicí vrstvy.

Metodická výhrada: jeden Python konzument je úzké hrdlo dřív než TimescaleDB →
výsledek je „cena TOHOTO ingesteru", ne zápisová kapacita DB. Pro strop DB by bylo
třeba víc konzumentů (shared subscription) — viz README.

Použití:
    python -m brokerbench.pipeline --broker pipeline-emqx \\
        --dsn postgresql://iot:iot-dev@localhost:5432/iot \\
        --db-container iot-timescaledb --rates 1000,5000,10000 --warmup --reset
"""
from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing as mp
import time
from pathlib import Path

import aiomqtt

from .bench import StepResult, _publisher_proc, median_step
from .docker_stats import sample_during
from .payload import parse_message, rows_from_message
from .stats import latency_summary

# Jednotky kanálů pro seed (kanonické, SenML-like).
QUANTITY_UNITS = {"co2": "ppm", "temp": "Cel", "rh": "%RH", "voc": "ppb", "pres": "hPa"}
# Měření v benchmark payloadu (payload._BASE).
BENCH_QUANTITIES = ("co2", "temp", "rh")
# Sloupce telemetry pro COPY (pořadí musí sedět s rows_from_message).
TELEMETRY_COLUMNS = ["time", "device_id", "channel_id", "value", "quality", "seq"]


def parse_rates(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip()]


def bench_device_ids(clients: int) -> list[str]:
    """ID zařízení, jak je generuje publisher (`bench._publisher_proc`)."""
    return [f"bench-{i:03d}" for i in range(clients)]


# ── DB pomocníci (asyncpg líně importovaný) ──────────────────────────────────

async def _connect(dsn: str):
    import asyncpg  # líný import — čisté funkce v payload.py nepotřebují DB vrstvu
    return await asyncpg.connect(dsn)


async def seed_devices(dsn: str, clients: int) -> None:
    """Idempotentně založí bench-000…bench-(N-1) + kanály co2/temp/rh.

    `telemetry` má FK na device i channel → bez seedu by COPY spadl.
    """
    conn = await _connect(dsn)
    try:
        for dev in bench_device_ids(clients):
            await conn.execute(
                "INSERT INTO device(device_id, hw_type) VALUES ($1, 'bench') "
                "ON CONFLICT (device_id) DO NOTHING",
                dev,
            )
            for q in BENCH_QUANTITIES:
                await conn.execute(
                    "INSERT INTO channel(device_id, quantity, unit) VALUES ($1, $2, $3) "
                    "ON CONFLICT (device_id, quantity) DO NOTHING",
                    dev, q, QUANTITY_UNITS[q],
                )
    finally:
        await conn.close()


async def reset_telemetry(dsn: str) -> None:
    """Vyprázdní telemetrii (čistý start měření). Pozn.: prázdná tabulka = nejlepší
    případ zápisu (malé indexy); reálná hypertable roste."""
    conn = await _connect(dsn)
    try:
        await conn.execute("TRUNCATE telemetry")
    finally:
        await conn.close()


async def db_durability(dsn: str) -> dict[str, str]:
    """Načte nastavení durability Postgresu — ovlivňuje latenci (fsync WAL)."""
    conn = await _connect(dsn)
    try:
        return {
            "synchronous_commit": await conn.fetchval("SHOW synchronous_commit"),
            "fsync": await conn.fetchval("SHOW fsync"),
        }
    finally:
        await conn.close()


# ── Měření CPU/RAM procesu ingesteru (psutil, líně) ──────────────────────────

async def _sample_ingester(pid: int, coro):
    """Spustí `coro` a vedle změří CPU/RAM procesu `pid` (konzumenta).

    Vrací (výsledek_coro, {cpu_pct, mem_mb_max}). Bez psutil → nuly (degraduje měkce).
    CPU se vzorkuje za běhu procesu (po jeho ukončení by `cpu_percent` selhal).
    """
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.cpu_percent(None)            # prime
    except Exception:
        return await coro, {"cpu_pct": 0.0, "mem_mb_max": 0.0}

    cpu_samples: list[float] = []
    rss_samples: list[int] = []
    stop = asyncio.Event()

    async def loop() -> None:
        while not stop.is_set():
            try:
                cpu_samples.append(proc.cpu_percent(None))
                rss_samples.append(proc.memory_info().rss)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(loop())
    try:
        result = await coro
    finally:
        stop.set()
        await task

    cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
    mem = max(rss_samples) / 1_048_576 if rss_samples else 0.0
    return result, {"cpu_pct": cpu, "mem_mb_max": mem}


# ── Ingestion proces (konzument → TimescaleDB) ───────────────────────────────

def _ingest_proc(host: str, port: int, dsn: str, device_ids: list[str], ready, stop,
                 result_q, sample_every: int, inflight: int, qos: int,
                 batch_size: int, flush_ms: float) -> None:
    async def run() -> None:
        conn = await _connect(dsn)
        rows = await conn.fetch(
            "SELECT id, device_id, quantity FROM channel WHERE device_id = ANY($1::text[])",
            device_ids,
        )
        channel_map = {(r["device_id"], r["quantity"]): r["id"] for r in rows}

        received = 0
        written = 0
        lat: list[float] = []
        batch: list[tuple] = []
        batch_msgs = 0
        pending_sampled: list[int] = []   # t_ns vzorkovaných zpráv v aktuální dávce
        last_flush = time.monotonic()
        flush_s = flush_ms / 1000.0

        async def flush() -> None:
            nonlocal batch, batch_msgs, written, pending_sampled, last_flush
            last_flush = time.monotonic()
            if not batch:
                return
            await conn.copy_records_to_table(
                "telemetry", records=batch, columns=TELEMETRY_COLUMNS,
            )
            commit_ns = time.time_ns()          # dávka je trvale v DB (durable dle synchronous_commit)
            for t_ns in pending_sampled:
                lat.append((commit_ns - t_ns) / 1e6)
            written += batch_msgs
            batch = []
            batch_msgs = 0
            pending_sampled = []

        async with aiomqtt.Client(
            host, port=port, identifier="pipeline-ingest",
            max_inflight_messages=inflight, max_queued_incoming_messages=0,
        ) as client:
            await client.subscribe("bench/#", qos=qos)
            ready.set()
            it = client.messages.__aiter__()
            while True:
                try:
                    msg = await asyncio.wait_for(it.__anext__(), timeout=0.5)
                except asyncio.TimeoutError:
                    await flush()               # časové vyprázdnění i při tichu
                    if stop.is_set():
                        break
                    continue
                except StopAsyncIteration:
                    break

                parsed = parse_message(msg.payload)
                if parsed is not None:
                    msg_rows = rows_from_message(parsed, channel_map)
                    if msg_rows:
                        received += 1
                        batch.extend(msg_rows)
                        batch_msgs += 1
                        if received % sample_every == 0:
                            pending_sampled.append(parsed[2])   # t_ns

                if len(batch) >= batch_size or (time.monotonic() - last_flush) >= flush_s:
                    await flush()
                if stop.is_set():
                    break
            await flush()                       # finální dávka

        await conn.close()
        result_q.put((received, written, lat))

    asyncio.run(run())


async def run_pipeline_step(host: str, port: int, dsn: str, device_ids: list[str],
                            target_rate: int, duration_s: float, clients: int, qos: int,
                            drain_s: float = 5.0, sample_every: int = 20, pub_procs: int = 4,
                            inflight: int = 1000, batch_size: int = 500,
                            flush_ms: float = 100.0) -> StepResult:
    """Jeden krok rampy: zátěž z publisherů → broker → ingestion → DB.

    CPU/RAM ingesteru se měří přes psutil; CPU/RAM DB řeší volající (sample_during).
    """
    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    stop = ctx.Event()
    result_q = ctx.Queue()
    sent_q = ctx.Queue()

    ing = ctx.Process(target=_ingest_proc,
                      args=(host, port, dsn, device_ids, ready, stop, result_q,
                            sample_every, inflight, qos, batch_size, flush_ms))
    ing.start()
    if not ready.wait(timeout=20):
        ing.terminate()
        raise RuntimeError("ingestion se nepřipojil včas (běží broker i TimescaleDB?)")

    async def _drive() -> tuple[int, int, int, list[float]]:
        # stejné rozdělení klientů jako broker-only (bench.run_step)
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

        await asyncio.sleep(drain_s)   # nech doputovat a zapsat zbytek (delší = míň falešné „ztráty")
        stop.set()
        try:
            received, written, lat = result_q.get(timeout=60)
        except Exception:
            received, written, lat = 0, 0, []
        ing.join(timeout=10)
        if ing.is_alive():
            ing.terminate()
        return sent, received, written, lat

    (sent, received, written, lat), ing_m = await _sample_ingester(ing.pid, _drive())

    throughput = written / duration_s if duration_s > 0 else 0.0
    loss_pct = max(0.0, (sent - written) / sent * 100.0) if sent else 0.0
    return StepResult(
        target_rate=target_rate, duration_s=duration_s,
        sent=sent, received=written, throughput=throughput, loss_pct=loss_pct,
        lat=latency_summary(lat),
        ing_cpu_pct=ing_m["cpu_pct"], ing_mem_mb=ing_m["mem_mb_max"],
    )


# ── CLI / rampa ──────────────────────────────────────────────────────────────

async def _one_step(args: argparse.Namespace, rate: int, device_ids: list[str]) -> StepResult:
    coro = run_pipeline_step(
        args.host, args.port, args.dsn, device_ids, rate, args.duration,
        args.clients, args.qos, drain_s=args.drain, sample_every=args.sample_every,
        inflight=args.inflight, batch_size=args.batch_size, flush_ms=args.flush_ms,
    )
    if args.db_container:
        step, metrics = await sample_during(args.db_container, coro)
        step.cpu_pct_avg = metrics["cpu_pct"]
        step.cpu_pct_max = metrics["cpu_pct"]
        step.mem_mb_avg = metrics["mem_mb_avg"]
        step.mem_mb_max = metrics["mem_mb_max"]
        return step
    return await coro


async def run_ramp(args: argparse.Namespace) -> list[StepResult]:
    device_ids = bench_device_ids(args.clients)
    print(f"  zakládám {args.clients} bench zařízení + kanály…", flush=True)
    await seed_devices(args.dsn, args.clients)
    if args.reset:
        await reset_telemetry(args.dsn)
        print("  telemetrie vyprázdněna (--reset)", flush=True)

    rates = parse_rates(args.rates)
    if args.warmup and rates:
        print("  zahřívací krok (zahazuje se — kvůli JIT/cache)…", flush=True)
        await _one_step(args, rates[0], device_ids)
        await asyncio.sleep(1.0)

    results: list[StepResult] = []
    for rate in rates:
        rep = max(1, args.repeat)
        print(f"  → krok: cíl {rate} zpráv/s, {args.duration}s, {args.clients} klientů × {rep}…",
              flush=True)
        runs = []
        for _ in range(rep):
            runs.append(await _one_step(args, rate, device_ids))
            await asyncio.sleep(0.5)
        step = median_step(runs)
        results.append(step)
        print(f"    uloženo {step.throughput:,.0f}/s · p99 {step.lat['p99']:.1f} ms · "
              f"ztráta {step.loss_pct:.1f}% · DB {step.cpu_pct_max:.0f}%/{step.mem_mb_max:.0f}MB · "
              f"ING {step.ing_cpu_pct:.0f}%/{step.ing_mem_mb:.0f}MB"
              f"{' (medián)' if rep > 1 else ''}", flush=True)
        await asyncio.sleep(1.0)
    return results


def print_table(broker: str, results: list[StepResult]) -> None:
    print(f"\n### {broker} — end-to-end (publish → uloženo v TimescaleDB)\n")
    print("| cíl/s | uloženo/s | ztráta % | p50 | p95 | p99 | max | DB CPU % | DB RAM MB "
          "| ING CPU % | ING RAM MB |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        print(f"| {r.target_rate:,} | {r.throughput:,.0f} | {r.loss_pct:.1f} "
              f"| {r.lat['p50']:.1f} | {r.lat['p95']:.1f} | {r.lat['p99']:.1f} | {r.lat['max']:.1f} "
              f"| {r.cpu_pct_max:.0f} | {r.mem_mb_max:.0f} "
              f"| {r.ing_cpu_pct:.0f} | {r.ing_mem_mb:.0f} |")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="brokerbench.pipeline",
        description="End-to-end benchmark: broker → ingestion → TimescaleDB")
    p.add_argument("--broker", default="pipeline",
                   help="popisek do tabulky/JSON (např. pipeline-emqx → série v grafech)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--dsn", default="postgresql://iot:iot-dev@localhost:5432/iot",
                   help="připojení k TimescaleDB (asyncpg)")
    p.add_argument("--db-container", default="iot-timescaledb",
                   help="kontejner DB pro měření CPU/RAM (prázdné = neměřit)")
    p.add_argument("--rates", default="500,1000,2500,5000,10000",
                   help="čárkou oddělené cílové rychlosti (zpráv/s)")
    p.add_argument("--duration", type=float, default=8.0, help="doba kroku v s")
    p.add_argument("--clients", type=int, default=20, help="počet publisher klientů / zařízení")
    p.add_argument("--qos", type=int, default=1, choices=[0, 1, 2])
    p.add_argument("--sample-every", type=int, default=20,
                   help="latenci měřit z každé N-té zprávy (menší = víc vzorků, méně šumu v p99)")
    p.add_argument("--inflight", type=int, default=1000,
                   help="in-flight okno QoS1 konzumenta")
    p.add_argument("--batch-size", type=int, default=500,
                   help="max řádků telemetrie v jedné dávce (COPY)")
    p.add_argument("--flush-ms", type=float, default=100.0,
                   help="max stáří dávky před zápisem (ms) — páka latence vs propustnost")
    p.add_argument("--drain", type=float, default=5.0,
                   help="doba doběhu po publikaci (s) — delší = míň falešné „ztráty")
    p.add_argument("--repeat", type=int, default=1, help="opakování kroku (medián)")
    p.add_argument("--warmup", action="store_true",
                   help="před měřením zahřívací krok (zahodí se) — kvůli JIT/cache")
    p.add_argument("--reset", action="store_true",
                   help="TRUNCATE telemetry před během (čistý start)")
    p.add_argument("--json", default=None, help="cesta pro uložení výsledků v JSON")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if not args.db_container:
        args.db_container = None
    dur = asyncio.run(db_durability(args.dsn))
    print(f"Pipeline benchmark '{args.broker}' (broker {args.host}:{args.port} → TimescaleDB) · "
          f"QoS {args.qos} · dávka {args.batch_size}/{args.flush_ms:.0f}ms · "
          f"synchronous_commit={dur['synchronous_commit']} · fsync={dur['fsync']}")
    results = asyncio.run(run_ramp(args))
    print_table(args.broker, results)
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"broker": args.broker, "qos": args.qos, "clients": args.clients,
             "duration_s": args.duration, "mode": "pipeline",
             "batch_size": args.batch_size, "flush_ms": args.flush_ms,
             "drain_s": args.drain, "durability": dur,
             "steps": [vars(r) for r in results]},
            indent=2))
        print(f"\nVýsledky uloženy do {out}")


if __name__ == "__main__":
    main()
