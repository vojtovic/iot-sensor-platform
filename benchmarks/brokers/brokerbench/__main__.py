"""CLI rampového benchmarku jednoho brokeru (běžícího na host:port).

Předpokládá, že broker už běží (např. ../../infra/broker.sh emqx).
Sám brokerem nehýbe — to dělá orchestrátor (orchestrate.py).

Příklad:
    python -m brokerbench --broker emqx --rates 1000,5000,10000 --duration 8
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .bench import StepResult, median_step, run_step
from .docker_stats import sample_during


def parse_rates(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip()]


async def _one_step(args: argparse.Namespace, rate: int) -> StepResult:
    """Jeden běh kroku (volitelně se vzorkováním CPU/RAM)."""
    if args.container:
        step, samples = await sample_during(
            args.container,
            run_step(args.host, args.port, rate, args.duration,
                     args.clients, args.qos, sample_every=args.sample_every,
                     inflight=args.inflight),
        )
        if samples:
            cpus = [s["cpu_pct"] for s in samples]
            mems = [s["mem_mb"] for s in samples]
            step.cpu_pct_avg = sum(cpus) / len(cpus)
            step.cpu_pct_max = max(cpus)
            step.mem_mb_avg = sum(mems) / len(mems)
            step.mem_mb_max = max(mems)
        return step
    return await run_step(args.host, args.port, rate, args.duration,
                          args.clients, args.qos, sample_every=args.sample_every,
                          inflight=args.inflight)


async def run_ramp(args: argparse.Namespace) -> list[StepResult]:
    results: list[StepResult] = []
    for rate in parse_rates(args.rates):
        rep = max(1, args.repeat)
        print(f"  → krok: cíl {rate} zpráv/s, {args.duration}s, "
              f"{args.clients} klientů × {rep}…", flush=True)
        runs = []
        for _ in range(rep):
            runs.append(await _one_step(args, rate))
            await asyncio.sleep(0.5)
        step = median_step(runs)
        results.append(step)
        print(f"    propustnost {step.throughput:,.0f}/s · "
              f"p99 {step.lat['p99']:.1f} ms · ztráta {step.loss_pct:.1f}% · "
              f"CPU {step.cpu_pct_max:.0f}% · RAM {step.mem_mb_max:.0f} MB"
              f"{' (medián)' if rep > 1 else ''}", flush=True)
        await asyncio.sleep(1.0)  # mezikrok — nech broker oddechnout
    return results


def print_table(broker: str, results: list[StepResult]) -> None:
    print(f"\n### {broker}\n")
    print("| cíl/s | propustnost/s | ztráta % | p50 ms | p95 ms | p99 ms | max ms | CPU % | RAM MB |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        print(f"| {r.target_rate:,} | {r.throughput:,.0f} | {r.loss_pct:.1f} "
              f"| {r.lat['p50']:.1f} | {r.lat['p95']:.1f} | {r.lat['p99']:.1f} "
              f"| {r.lat['max']:.1f} | {r.cpu_pct_max:.0f} | {r.mem_mb_max:.0f} |")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brokerbench", description="Rampový benchmark MQTT brokeru")
    p.add_argument("--broker", default="broker", help="popisek brokeru (do tabulky/JSON)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--rates", default="500,1000,2500,5000,10000,20000",
                   help="čárkou oddělené cílové rychlosti (zpráv/s)")
    p.add_argument("--duration", type=float, default=8.0, help="doba kroku v s")
    p.add_argument("--clients", type=int, default=20, help="počet publisher klientů")
    p.add_argument("--qos", type=int, default=1, choices=[0, 1, 2])
    p.add_argument("--sample-every", type=int, default=20,
                   help="latenci měřit z každé N-té zprávy (odlehčí subscriber)")
    p.add_argument("--inflight", type=int, default=1000,
                   help="in-flight okno QoS1 subscriberu (paho default je 20)")
    p.add_argument("--repeat", type=int, default=1,
                   help="kolikrát zopakovat každý krok (reportuje se medián)")
    p.add_argument("--container", default=None,
                   help="jméno docker kontejneru brokeru pro měření CPU/RAM (volitelné)")
    p.add_argument("--json", default=None, help="cesta pro uložení výsledků v JSON")
    return p


def main() -> None:
    args = build_parser().parse_args()
    print(f"Benchmark brokeru '{args.broker}' na {args.host}:{args.port} "
          f"(QoS {args.qos})")
    results = asyncio.run(run_ramp(args))
    print_table(args.broker, results)
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"broker": args.broker, "qos": args.qos, "clients": args.clients,
             "duration_s": args.duration,
             "steps": [vars(r) for r in results]},
            indent=2))
        print(f"\nVýsledky uloženy do {out}")


if __name__ == "__main__":
    main()
