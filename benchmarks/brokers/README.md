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

## Výsledky

Běh 2026-06-07 (rates 1k–10k · 6 s/krok · 20 klientů · QoS 1; laptop, jeden host).
Raw data: `results/summary-20260607-083020.md` + JSONy (gitignored).

### Srovnání při 5 000 zpráv/s (čistý bod — skoro všichni 0 ztrát)

Seřazeno podle efektivity (RAM + latence):

| Broker | propust./s | ztráta % | p99 ms | CPU % | RAM MB |
|---|---:|---:|---:|---:|---:|
| **NanoMQ** | 5 000 | 0 | **12.5** | 0 | **3** |
| **Mosquitto** | 5 000 | 0 | 16.1 | 0 | **4** |
| **VerneMQ** | 5 000 | 0 | 15.1 | 2 | 205 |
| **Artemis** | 5 000 | 0 | 35.9 | 4 | 616 |
| **RabbitMQ** | 5 000 | 0 | 36.4 | 309 | 181 |
| **EMQX** | 5 000 | 0 | 138.3 | 14 | 252 |
| **HiveMQ CE** | 1 276 | 74.5 | 874 | 34 | 440 |

### Co z toho plyne

- **NanoMQ a Mosquitto = jednoznační šampioni efektivity:** ~3–4 MB RAM (!),
  nejnižší latence, a oba udrželi i 10 000 zpráv/s s 0 ztrátami. Pro edge /
  malé nasazení ideální.
- **VerneMQ:** čistý do 5 000/s s rozumnou RAM, ale od 7 500/s CPU vyskočí na
  ~105 % a začne ztrácet.
- **Artemis:** zvládl i 10 000/s bez ztrát, ale nejtěžší na RAM (~620 MB, JVM).
- **RabbitMQ:** funguje, ale MQTT je tu přes plugin nad AMQP → **vysoké CPU**
  (300 %+ i při 1 000/s) a strop ~5 000/s. MQTT není jeho hlavní disciplína.
- **EMQX:** stabilní, ale vyšší latence při 5 000/s než lehké brokery; síla je
  ve featurách (dashboard, shared subs, MQTT 5), ne v minimální stopě.
- **HiveMQ CE:** v tomto testu **propadl** — vysoká latence už od 1 000/s a od
  2 500/s velké ztráty. Pravděpodobně výchozí konfigurace / JVM warmup /
  malé fronty CE edice; zaslouží si bližší pohled (zatím bráno jako naměřeno).

### Výhrady ke konkrétním číslům

- **Jeden běh, krátké kroky (6 s)** → latence u „kolena" jsou hodně proměnlivé
  (např. Mosquitto 7 500→664 ms, ale 10 000→200 ms je šum, ne trend). Pro
  publikovatelná čísla opakovat víckrát a delší kroky.
- **CPU z `docker stats`** je vzorkované a šumí (proto u zahlcení občas
  paradoxně nízké — broker čeká na zahlcený ack/klient, nepočítá).
- Strop ~10 000/s je **klientský** (viz výhrada výše), ne brokeru.
