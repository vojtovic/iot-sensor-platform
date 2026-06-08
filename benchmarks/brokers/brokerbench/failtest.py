"""Test spolehlivosti při výpadku brokeru (durability).

Scénář (deterministický):
  1. Subscriber si založí TRVALOU session (clean_session=False) + odběr, odpojí se.
  2. Publisher pošle N zpráv se seq 1..N (QoS 1) — broker je zařadí do fronty
     pro odpojeného trvalého subscribera.
  3. (volitelně) restart brokeru — `docker restart`.
  4. Subscriber se znovu připojí (stejné id, clean_session=False) → broker by
     mu měl doručit frontu.
  5. Analýza přijatých seq: mezery = ztráta, opakování = duplikáty.

Bez restartu (kontrola) se ověří jen podpora trvalé session + offline fronty.
S restartem se ověří, zda fronta PŘEŽIJE pád brokeru (persistence na disk).
Používá MQTT 3.1.1 + clean_session kvůli jednoduché sémantice trvalé session.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import aiomqtt
from paho.mqtt.client import MQTTv311

TOPIC = "fail/seq"
SUB_ID = "fail-sub"
PUB_ID = "fail-pub"


@dataclass
class FailResult:
    n: int
    received_unique: int
    lost: int            # kolik seq z 1..N nedorazilo
    duplicates: int      # kolik zpráv přišlo navíc (opakované seq)
    restarted: bool


async def _establish_session(host: str, port: int) -> None:
    """Připojí subscribera s trvalou session, přihlásí odběr a odpojí se."""
    async with aiomqtt.Client(host, port=port, identifier=SUB_ID,
                              protocol=MQTTv311, clean_session=False) as c:
        await c.subscribe(TOPIC, qos=1)
        await asyncio.sleep(0.5)  # ať se SUBSCRIBE projeví na brokeru


async def _publish_n(host: str, port: int, n: int) -> None:
    async with aiomqtt.Client(host, port=port, identifier=PUB_ID,
                              protocol=MQTTv311) as c:
        for i in range(1, n + 1):
            await c.publish(TOPIC, str(i), qos=1)


async def _collect(host: str, port: int, drain_s: float) -> list[int]:
    """Připojí trvalého subscribera a sbírá doručené seq, dokud zprávy chodí."""
    seqs: list[int] = []
    async with aiomqtt.Client(host, port=port, identifier=SUB_ID,
                              protocol=MQTTv311, clean_session=False) as c:
        # po reconnectu se NEpřihlašujeme znovu — odběr je součástí trvalé session
        it = c.messages.__aiter__()
        while True:
            try:
                msg = await asyncio.wait_for(it.__anext__(), timeout=drain_s)
            except asyncio.TimeoutError:
                break
            except StopAsyncIteration:
                break
            try:
                seqs.append(int(msg.payload))
            except ValueError:
                pass
    return seqs


async def wait_broker_ready(host: str, port: int, timeout_s: float = 120) -> bool:
    """Počká, až broker skutečně přijme MQTT připojení (ne jen TCP port).

    JVM brokery (HiveMQ, Artemis) otevřou port dřív, než jsou připravené —
    proto zkoušíme reálný MQTT connect a opakujeme, dokud neuspěje.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            async with aiomqtt.Client(host, port=port, identifier="fail-probe",
                                      protocol=MQTTv311, timeout=5):
                return True
        except Exception:
            await asyncio.sleep(2)
    return False


async def run_failtest(host: str, port: int, n: int,
                       restart_container: str | None = None,
                       drain_s: float = 4.0) -> FailResult:
    await _establish_session(host, port)
    await _publish_n(host, port, n)

    restarted = False
    if restart_container:
        proc = await asyncio.create_subprocess_exec(
            "docker", "restart", restart_container,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if not await wait_broker_ready(host, port):
            raise RuntimeError(f"{restart_container} po restartu nenaběhl")
        await asyncio.sleep(2)  # ať broker dokončí obnovu session
        restarted = True

    seqs = await _collect(host, port, drain_s)

    unique = set(seqs)
    in_range = {s for s in unique if 1 <= s <= n}
    lost = n - len(in_range)
    duplicates = len(seqs) - len(unique)
    return FailResult(
        n=n,
        received_unique=len(in_range),
        lost=lost,
        duplicates=duplicates,
        restarted=restarted,
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        prog="brokerbench.failtest",
        description="Test spolehlivosti brokeru při výpadku (durability)",
    )
    ap.add_argument("--broker", default="broker", help="popisek do výstupu")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--n", type=int, default=500, help="počet zpráv (seq 1..N)")
    ap.add_argument("--container", default=None,
                    help="docker kontejner brokeru pro restart (oba běhy: kontrola + restart)")
    ap.add_argument("--json", default=None, help="cesta pro uložení výsledku v JSON")
    args = ap.parse_args()

    def line(res: FailResult) -> str:
        typ = "S RESTARTEM" if res.restarted else "bez restartu (kontrola)"
        return (f"[{args.broker}] {typ}: posláno {res.n}, doručeno {res.received_unique}, "
                f"ztráta {res.lost} ({res.lost / res.n * 100:.1f} %), duplikáty {res.duplicates}")

    # kontrola (bez restartu)
    ctrl = asyncio.run(run_failtest(args.host, args.port, args.n))
    print(line(ctrl))
    rest = None
    if args.container:
        rest = asyncio.run(run_failtest(args.host, args.port, args.n,
                                        restart_container=args.container))
        print(line(rest))

    if args.json:
        import json
        from pathlib import Path
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "broker": args.broker, "n": args.n,
            "control": {"lost": ctrl.lost, "duplicates": ctrl.duplicates},
            "restart": ({"lost": rest.lost, "duplicates": rest.duplicates}
                        if rest else None),
        }, indent=2))


if __name__ == "__main__":
    main()
