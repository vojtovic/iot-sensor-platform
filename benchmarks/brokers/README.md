# benchmarks/brokers/ — porovnání MQTT brokerů

Rampový benchmark 7 MQTT brokerů (viz [../../infra/](../../infra/#porovnání-mqtt-brokerů)).
**Samostatný experiment** oddělený od benchmarku backendových stacků (Fáze 3) —
mění se jen broker, vše ostatní je stejné (bod 2 zadání).

## Co se měří

Pro každý broker se projede **rampa** rostoucích cílových rychlostí. V každém
kroku se měří:

- **propustnost** — kolik zpráv/s reálně dorazí end-to-end,
- **latence** — p50 / p95 / p99 / max (publish → receive),
- **ztrátovost** — kolik z odeslaných nedorazilo v okně (indikátor saturace),
- **zdroje brokeru** — CPU % a RAM kontejneru (`docker stats`).

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

Seřazeno podle latence (p99). RAM/CPU = max kontejneru během kroku.

**QoS 1** (telemetrie — doručení potvrzené ackem):

| Broker | propust./s | ztráta % | p99 ms | CPU % | RAM MB |
|---|---:|---:|---:|---:|---:|
| **NanoMQ** | 5 000 | 0 | **14.2** | 0 | **3** |
| **Artemis** | 5 000 | 0 | 25.8 | 0 | 639 |
| **Mosquitto** | 5 000 | 0 | 28.6 | 0 | **4** |
| **VerneMQ** | 5 000 | 0 | 32.7 | 0 | 360 |
| **EMQX** | 5 000 | 0 | 52.7 | 10 | 248 |
| **RabbitMQ** | 4 996 | 0 | 707.8 | 19 | 267 |
| **HiveMQ CE** | 1 246 | 75.1 | 867.7 | 11 | 657 |

**QoS 0** (bez potvrzování — maximální propustnost):

| Broker | propust./s | ztráta % | p99 ms | CPU % | RAM MB |
|---|---:|---:|---:|---:|---:|
| **Artemis** | 5 000 | 0 | 5.5 | 0 | 676 |
| **Mosquitto** | 5 000 | 0 | 6.2 | 0 | **4** |
| **NanoMQ** | 5 000 | 0 | 8.9 | 0 | **3** |
| **VerneMQ** | 5 000 | 0 | 10.1 | 0 | 108 |
| **EMQX** | 5 000 | 0 | 15.3 | 9 | 251 |
| **RabbitMQ** | 5 000 | 0 | 15.8 | 1 | 147 |
| **HiveMQ CE** | 5 000 | 0 | 21.6 | 3 | 520 |

### Co z toho plyne

- **NanoMQ a Mosquitto = šampioni efektivity:** ~3–4 MB RAM (!), nízká latence
  v obou QoS, drží i 10 000/s. Pro edge / malé nasazení ideální.
- **QoS 1 vs QoS 0 = kompromis durabilita vs. propustnost.** Při QoS 0 zvládnou
  5 000/s úplně všichni (i HiveMQ). Při QoS 1 se rozevřou nůžky:
  - **RabbitMQ** udrží 5 000/s, ale p99 vyletí na ~700 ms (MQTT přes AMQP plugin).
  - **HiveMQ CE** spadne na ~1 250/s se ztrátami — jeho QoS 1 cesta je
    disk-bound (persistuje zprávy), což je **vlastnost, ne vada**: vyměňuje
    propustnost za odolnost. Strop ~1 250/s je nezávislý na počtu klientů i
    velikosti in-flight okna → limit je server-side, ne klientský.
- **Artemis a VerneMQ:** zvládnou obojí, ale těžší na RAM (JVM / Erlang).
- **EMQX:** stabilní střed; jeho síla jsou featury (dashboard, shared subs,
  MQTT 5), ne minimální stopa.

### Grafy

V `results/export/` (po `python -m brokerbench.export`):
`throughput-qos{0,1}.png`, `latency-p99-qos{0,1}.png`, `ram-qos{0,1}-5000.png`,
`cpu-qos{0,1}-5000.png`.

### Výhrady ke konkrétním číslům

- **Jeden host** (Python klient i brokery sdílí CPU) → strop ~10 000/s je
  **klientský**, ne brokeru. Čísla jsou relativní (stejný klient pro všechny).
- **CPU z `docker stats`** je vzorkované a šumí.
- Pro publikovatelná čísla: víc klientských strojů / `emqtt_bench` (TESTING.md §5).
