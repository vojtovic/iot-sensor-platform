# benchmarks/brokers/ — porovnání MQTT brokerů

Rampový benchmark 7 MQTT brokerů (viz [../../infra/](../../infra/#porovnání-mqtt-brokerů)).
**Samostatný experiment** oddělený od benchmarku backendových stacků (Fáze 3) —
mění se jen broker, vše ostatní je stejné (bod 2 zadání).

## Co je QoS (úroveň doručení MQTT)

MQTT definuje tři úrovně kvality doručení zprávy (Quality of Service). Měříme
hlavně QoS 0 a QoS 1, protože ty se v IoT reálně používají:

- **QoS 0 — „at most once" (nejvýše jednou):** odesílatel pošle zprávu a dál se
  o ni nestará. Žádné potvrzení, žádné opakování — když se zpráva po cestě
  ztratí (výpadek, přetížení), je pryč. **Nejrychlejší a nejlevnější**, ale bez
  záruky doručení. Hodí se pro častá, „jednorázová" měření, kde občasná ztráta
  nevadí.
- **QoS 1 — „at least once" (alespoň jednou):** příjemce každou zprávu potvrdí
  (PUBACK). Když potvrzení nepřijde, odesílatel zprávu **pošle znovu** → zpráva
  dorazí zaručeně, ale může i víckrát (proto má telemetrie `seq` na deduplikaci).
  Dražší (ack + případná persistence na straně brokeru), ale spolehlivá.
  **Výchozí volba pro telemetrii v tomto projektu** (ROADMAP §6).
- **QoS 2 — „exactly once" (právě jednou):** čtyřfázový handshake, zaručeně bez
  duplikátů. Nejdražší; pro telemetrii senzorů se prakticky nepoužívá, proto ho
  neměříme.

**Proč měříme obojí:** rozdíl QoS 0 vs QoS 1 je přímo ten **kompromis rychlost
vs. spolehlivost**. U QoS 0 jsou si brokery blízko; u QoS 1 se ukáže, jak dobře
zvládají potvrzování a (ne)persistenci — tam se nejvíc liší (viz Výsledky).

## Co se měří

Pro každý broker se projede **rampa** rostoucích cílových rychlostí. V každém
kroku se měří:

- **propustnost** — kolik zpráv/s reálně dorazí end-to-end,
- **latence** — p50 / p95 / p99 / max (publish → receive),
- **ztrátovost** — kolik z odeslaných nedorazilo v okně (indikátor saturace),
- **zdroje brokeru** — CPU a RAM kontejneru (čteno z cgroup v2 — viz výhrady).

„Koleno" rampy = krok, kde propustnost přestane stíhat cíl a latence vyskočí.

## Spuštění

```bash
cd benchmarks/brokers/
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# celá sada (zastaví/spustí brokery sám přes ../../infra/broker.sh)
./run_all.sh
# nebo vybrané brokery / parametry
RATES=1000,5000,10000 DURATION=8 ./run_all.sh emqx mosquitto

# jeden broker, který už běží na localhost:1883
python -m brokerbench --broker emqx --container iot-emqx --rates 1000,5000,10000
```

> Vyžaduje docker. Dokud nemáš docker bez sudo, spouštěj přes
> `sg docker -c './run_all.sh'`. Výsledky (JSON + souhrn) jdou do `results/`
> (gitignored).

### Stabilnější čísla (opakování, QoS, in-flight okno)

```bash
REPEAT=3 DURATION=8 ./run_all.sh          # každý krok 3× → medián
QOS=0 ./run_all.sh                        # QoS 0 (bez ack flow control)
```

| Proměnná | Default | Význam |
|---|---|---|
| `REPEAT` / `--repeat` | 1 | opakování kroku (reportuje se medián) |
| `QOS` / `--qos` | 1 | QoS publikace i odběru |
| `INFLIGHT` / `--inflight` | 1000 | in-flight okno QoS1 subscriberu (paho default 20) |

## Export výsledků

Z `results/*.json` vygeneruje CSV, grafy a souhrnnou tabulku:

```bash
pip install -e ".[viz]"                   # matplotlib pro grafy (jednorázově)
python -m brokerbench.export              # → results/export/
python -m brokerbench.export --ref-rate 5000
```

Vznikne:
- `results/export/benchmark.csv` — všechny brokery × kroky (do Excelu/Sheets),
- `results/export/summary.md` — souhrnná tabulka v referenčním bodě (per QoS),
- `results/export/*.png` — grafy: propustnost a p99 latence vs cíl, RAM a CPU
  per broker (zvlášť pro každý QoS).

CSV a souhrn fungují i bez matplotlib; grafy ho vyžadují.

### Parametry

| Proměnná / přepínač | Default | Význam |
|---|---|---|
| `RATES` / `--rates` | `1000,2500,5000,7500,10000` | cílové rychlosti rampy (zpráv/s) |
| `DURATION` / `--duration` | 6 | doba kroku (s) |
| `CLIENTS` / `--clients` | 20 | počet publisher klientů |
| `--qos` | 1 | QoS (telemetrie dle ROADMAP) |
| `SAMPLE_EVERY` / `--sample-every` | 50 | latenci měřit z každé N-té zprávy |

## Architektura

Subscriber a publisheři běží v **oddělených procesech** (multiprocessing).
Kdyby sdíleli jednu asyncio smyčku, publisheři by ji zahltili a subscriber by
nestíhal → umělý strop daný klientem (na tomto stroji ~3k zpráv/s). Oddělení
procesů ho posunulo na ~9–10k zpráv/s.

## Metodická výhrada (důležité)

Měření běží na **jednom hostu** (Python klient i brokery sdílí CPU). Python
klient se stává úzkým hrdlem dřív, než výkonné brokery narazí na svůj strop.
Proto:

- čísla jsou **relativní** (stejný klient pro všechny brokery), ne absolutní
  maximum brokeru,
- u nízké/střední zátěže (kde je ztráta 0) jsou **latence a CPU/RAM** nejvíc
  vypovídající,
- pro absolutní throughput by bylo třeba víc klientských strojů nebo
  specializovaný nástroj (`emqtt_bench`, `k6`) — viz TESTING.md §5.

## Testovací prostředí

Všechny brokery i klient běžely na **jednom stroji** (sdílí CPU — viz výhrady níže).

| Komponenta | Specifikace |
|---|---|
| CPU | Intel Core i5-12450HX (8 jader / 12 vláken) |
| RAM | 23 GiB |
| Disk | NVMe SSD (WDC SN530 / Micron) |
| OS | Arch Linux, kernel 6.19.9 |
| Docker | 29.4.3 |
| Klient | Python 3.14, aiomqtt (multiprocessing) |

Verze brokerů: EMQX 5.8 · Mosquitto 2 · NanoMQ 0.22 · HiveMQ CE 2024.3 ·
VerneMQ 1.13 · RabbitMQ 3.13 · ActiveMQ Artemis 2.37. Všichni s výchozí
konfigurací (anonymní přístup), QoS dle běhu.

## Výsledky

Běh 2026-06-07 (rates 1k–10k · 8 s/krok · **medián ze 3 opakování** · 20 klientů;
jeden host — viz výše). Grafy a CSV: `results/export/` (vygeneruj `python -m brokerbench.export`).

### Srovnání při 5 000 zpráv/s

Seřazeno podle latence (p99). CPU = průměr přes krok (% jednoho jádra, cgroup),
RAM = working set kontejneru (memory.current − cache).

**QoS 1** (telemetrie — doručení potvrzené ackem):

| Broker | propust./s | ztráta % | p99 ms | CPU % | RAM MB |
|---|---:|---:|---:|---:|---:|
| **Mosquitto** | 5 000 | 0 | **11.8** | **16** | 11 |
| **NanoMQ** | 5 000 | 0 | 14.8 | 66 | **8** |
| **Artemis** | 5 000 | 0 | 18.4 | 61 | 674 |
| **VerneMQ** | 5 000 | 0 | 32.1 | 122 | 376 |
| **EMQX** | 5 000 | 0 | 56.8 | 200 | 249 |
| **RabbitMQ** | 5 000 | 0 | 487.7 | 132 | 268 |
| **HiveMQ CE** | 1 244 | 75.1 | 865.4 | 88 | 603 |

**QoS 0** (bez potvrzování — maximální propustnost):

| Broker | propust./s | ztráta % | p99 ms | CPU % | RAM MB |
|---|---:|---:|---:|---:|---:|
| **NanoMQ** | 5 000 | 0 | **5.6** | 38 | 11 |
| **Mosquitto** | 5 000 | 0 | 6.5 | **13** | **7** |
| **VerneMQ** | 5 000 | 0 | 8.7 | 56 | 111 |
| **HiveMQ CE** | 5 000 | 0 | 11.0 | 83 | 524 |
| **Artemis** | 5 000 | 0 | 11.1 | 44 | 687 |
| **RabbitMQ** | 5 000 | 0 | 11.6 | 84 | 148 |
| **EMQX** | 5 000 | 0 | 16.9 | 132 | 254 |

**QoS 0 — hledání stropu (rampa 5k → 30k):** protože při 5 000/s je propustnost
nezajímavá (všichni stíhají), byla QoS 0 změřena i do 30 000/s:

| Cílová rychlost | Chování |
|---|---|
| do **15 000/s** | všichni 0 ztrát, latence roste úměrně |
| **20 000/s** | většinou ještě 0 ztrát, ale p99 vyletí na 3–6 s (roste backlog) |
| **25 000/s** | první ztráty (Mosquitto 5 %, ostatní 12–36 %) |
| **30 000/s** | saturace, ztráty 30–49 %, propustnost klesá na ~13–18k |

Strop ~**20 000/s** je z větší části daný **klientem** (jeden subscriber proces),
ne brokery — ale i tak se projevily rozdíly: **RabbitMQ láme nejdřív** (p99 už
u 10 000/s skočí na ~1,5 s, ostatní pod 120 ms), **Mosquitto drží nejdéle**
(ještě 25k s pouhými 5 % ztrát).

### Co z toho plyne

- **Mosquitto = nejvyrovnanější:** nejnižší CPU (13–16 %) i RAM (~7–11 MB) a
  nejnižší latence při QoS 1. Pro malé/edge nasazení ideální.
- **NanoMQ:** stejně malá RAM, ale vyšší CPU (chytřejší busy-polling NNG).
  Skvělá latence při QoS 0.
- **QoS 1 vs QoS 0 = kompromis durabilita vs. propustnost.** Při QoS 0 zvládnou
  5 000/s úplně všichni (i HiveMQ). Při QoS 1 se rozevřou nůžky:
  - **RabbitMQ** udrží 5 000/s, ale p99 vyletí na ~490 ms (MQTT přes AMQP plugin).
  - **HiveMQ CE** spadne na ~1 250/s se ztrátami — jeho QoS 1 cesta je
    disk-bound (persistuje zprávy), což je **vlastnost, ne vada**: vyměňuje
    propustnost za odolnost. Strop ~1 250/s je nezávislý na počtu klientů i
    velikosti in-flight okna → limit je server-side, ne klientský.
- **EMQX:** nejvyšší CPU (132–200 %, Erlang VM), ale stabilní; síla jsou featury
  (dashboard, shared subs, MQTT 5), ne minimální stopa.
- **Artemis / VerneMQ:** zvládnou obojí, ale těžší na RAM (JVM ~680 MB / Erlang).

### Grafy

Klíčové grafy pro QoS 1 (kompletní sada vč. QoS 0 je ve `charts/`; generuje
`python -m brokerbench.export`):

**Latence p99 vs zatížení** — kde který broker „láme" (log škála):

![Latence p99, QoS 1](charts/latency-p99-qos1.png)

HiveMQ narazí na zeď hned u 2 500/s, RabbitMQ u 5 000/s; lehké brokery drží nízko nejdéle.

**Propustnost vs cíl** — sledování ideální linie:

![Propustnost, QoS 1](charts/throughput-qos1.png)

NanoMQ/Mosquitto/Artemis sledují ideál až do 10 000/s; HiveMQ je placatý na ~1 250/s.

**CPU a RAM při 5 000/s:**

![CPU, QoS 1](charts/cpu-qos1-5000.png)
![RAM, QoS 1](charts/ram-qos1-5000.png)

Mosquitto má zdaleka nejnižší CPU; EMQX nejvyšší (Erlang VM). RAM: lehké brokery
jednotky MB vs. JVM/Erlang stovky MB.

**Propustnost QoS 0 (rampa do 30 000/s)** — kde se odlomí od ideálu:

![Propustnost, QoS 0](charts/throughput-qos0.png)

Všichni sledují ideál do ~20 000/s, pak saturace. Mosquitto (červená) vyjede
nejvýš, RabbitMQ (hnědá) láme nejdřív (~15k). Strop je z větší části klientský
(jeden subscriber), ale RabbitMQ se odlišil reálně.

### Výhrady ke konkrétním číslům

- **Jeden host** (Python klient i brokery sdílí CPU) → strop propustnosti
  (~20 000/s QoS 0) je z větší části **klientský** (jeden subscriber proces), ne
  brokeru. Čísla jsou relativní (stejný klient pro všechny).
- **CPU/RAM** se čte z cgroup v2 (`cpu.stat` usage_usec, `memory.current`);
  CPU je průměr přes celý krok (dřívější `docker stats` vzorkování dávalo u
  lehkých brokerů chybně 0 %).
- Pro publikovatelná čísla: víc klientských strojů / `emqtt_bench` (TESTING.md §5).
