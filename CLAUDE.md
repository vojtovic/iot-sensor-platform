# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Co to je

Semestrální projekt: **distribuovaný IoT systém pro sběr senzorických dat v budovách**
(HVAC / kvalita vnitřního prostředí — teplota, vlhkost, CO₂, VOC, tlak). Postupuje
po fázích z [ROADMAP.md](ROADMAP.md) (Fáze 0–6); body 1–7 zadání jsou v rozsahu,
body 8–12 `[NAVAZUJÍCÍ]`. Testovací strategie v [TESTING.md](TESTING.md).

> Komunikace i commit messages jsou **česky**.

## Architektura (datový tok)

```
senzory ──MQTT──> broker ──> ingestion ──> TimescaleDB ─┐
(simulátor)        (EMQX)     (.NET)        (telemetrie  ├─> API ──> dashboard
                     │                       + metadata) │   (REST/WS)  (Grafana)
                     └── device registry + konfigurace ──┘
```

- **Broker = EMQX** (rozhodnuto benchmarkem — [ADR 0004](docs/adr/0004-vyber-mqtt-brokeru.md)).
  Durabilita přes `EMQX_DURABLE=true` (durable sessions, ověřeno failtestem).
- **Backend stack = .NET / C#** (rozhodnuto benchmarkem — [ADR 0001](docs/adr/0001-vyber-implementacniho-stacku.md)).
  Plný backend (ingestion + REST/WS API + device registry) se staví ve **Fázi 4** do `backend/`
  (zatím prázdné; odrazový můstek je prototyp `benchmarks/dotnet/`).
- **DB = TimescaleDB** — telemetrie (hypertable) i relační metadata v jednom Postgresu.
  Datový model (ROADMAP §5): `tenant → site → location → device → channel`, `telemetry`
  hypertable; modularita = zařízení má N kanálů. Schéma v `infra/timescale/init/*.sql`.
- **Protokol** (ROADMAP §6): MQTT 5, topic `v1/dev/{device_id}/telemetry`, JSON payload
  se `seq` (monotónní čítač → řazení, **dedup**, replay). Dedup je věc ingestion vrstvy,
  ne unikátního indexu (TimescaleDB vyžaduje partitioning sloupec v unique indexu).
- **Klíčový nález z benchmarků:** úzké hrdlo pipeline je **ingestion konzument**, ne broker
  ani DB → škálovat se má ingestion vrstva (víc konzumentů / shared subscriptions).

## Infrastruktura — spuštění (`infra/`)

Konfigurace přes profily v `docker-compose.yml`; aktivní profily z `infra/.env`
(`COMPOSE_PROFILES=platform,emqx`). **Vždy běží jen jeden broker** (všechny mapují :1883).

```bash
cd infra/
cp .env.example .env
docker compose up -d                 # platform (TimescaleDB+Grafana) + EMQX
./broker.sh mosquitto                # přepni broker (down vše + up vybraný profil)
./broker.sh down                     # zastav vše
docker compose --profile '*' down    # zastav VČETNĚ neaktivních profilů (běžné `down` respektuje profily!)
```

Brokery (každý vlastní profil): `emqx mosquitto nanomq hivemq vernemq rabbitmq artemis`.
Init SQL skripty běží **jen při prvním startu** (prázdný volume) → po změně schématu `docker compose down -v`.

## Simulátor (`simulator/`)

```bash
cd simulator/
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
python -m simulator --devices 2 --rate 1      # publikuje telemetrii dle §6
pytest -q                                       # unit testy (bez brokeru)
```

## Benchmarky (`benchmarks/`)

Hlavní nástroj je python balíček **`brokerbench`** v `benchmarks/brokers/` (vlastní venv).
Tři měřicí roviny + výběr stacku:

```bash
cd benchmarks/brokers/
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev,viz,db]"
pytest -q                            # 15 unit testů (pure funkce: stats, payload, pipeline)

./run_all.sh                         # broker výkon (rampa propustnost/latence/CPU/RAM, QoS 0/1)
./run_failtest.sh                    # spolehlivost: restart brokeru → ztráty/dup (durabilita)
./run_scaletest.sh                   # škálovatelnost počtu souběžných spojení
./run_pipeline.sh                    # end-to-end: broker → ingestion → TimescaleDB
./run_stacks.sh python node dotnet java   # benchmark backend stacků (ingestion služby)

python -m brokerbench.export         # CSV + grafy → results/export/ (pak cp do charts/)
```

- Kandidátní ingestion služby (Fáze 3) jsou kontejnerizované: `benchmarks/{python-fastapi,node-nestjs,dotnet,java-spring}/` — **stejný kontrakt** (MQTT subscribe → parse → dávkový COPY do TimescaleDB, `time` = `t_ns` kvůli měření latence z DB).
- `brokerbench` měří **zvenčí**: zátěž = publisher; propustnost/latence z DB; CPU/RAM z **cgroup v2** (`docker_stats.py`) — `docker stats` u lehkých kontejnerů dával chybně 0 % CPU.
- `results/` je gitignored (raw data + souhrny); **grafy se ručně kopírují do `benchmarks/brokers/charts/`** (verzované, do textu práce).
- Metodická výhrada (uváděj v závěrech): Python klient na jednom hostu je strop dřív než výkonné brokery → čísla jsou **relativní**, ne absolutní max.

## Konvence

- **Commity česky, prefix fází** (`Fáze 2: ...`), tělo + řádek `Ověřeno:` s důkazem (co se spustilo).
- **Lineární historie na `main`** (solo projekt), malé reviewovatelné commity (jedna komponenta).
- **Ověřuj spuštěním**, ne jen napsáním — nahoď kontejner, zkontroluj DB, udělej MQTT round-trip, než prohlásíš „hotovo".
- Rozhodnutí se píšou do **ADR** (`docs/adr/`); externí zdroje pro citace do `docs/reference/externi-zdroje.md` (doplňuj při každé rešerši).

## Prostředí / gotchas

- **Docker bez sudo:** pokud uživatel není ve skupině `docker` (nebo session předchází přidání), spouštěj docker příkazy přes `sg docker -c '...'`.
- **EMQX se konfiguruje přes env proměnné** v compose, ne přes mountnutý `emqx.conf` (přepsání souboru rozbije výchozí listenery/dashboard). Durable sessions vyžadují `cluster.discovery_strategy=singleton`.
- Data brokeru/DB v **pojmenovaných volumech** (ne bind mount — řeší permission problémy).
- `scaletest` zvedá fd limit; brokery mají v compose `ulimits: nofile 65536` (default kontejneru 1024 stropoval ~1000 spojení).
