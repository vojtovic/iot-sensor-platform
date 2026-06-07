# infra/

Lokální vývojové a testovací prostředí (Docker).

## Stav

Postupuje se po krocích Fáze 2 (viz [ROADMAP](../ROADMAP.md#fáze-2--sdílená-infrastruktura-základ-pro-bod-4--1-týden)):

- [x] **MQTT broker (EMQX)** — dashboard, listenery 1883 / 8083 / 18083
- [x] **TimescaleDB** — telemetrie (hypertable) + metadata v jednom Postgresu
- [x] **Init skripty schématu** (`§5` model + seed data)
- [x] **Grafana** — provisioned datasource → TimescaleDB

> Infrastruktura Fáze 2 je hotová (broker + DB + Grafana + [simulátor](../simulator/)).
> Navíc je k dispozici **sada 7 MQTT brokerů k porovnání** — viz níže.

## Rychlý start

```bash
cd infra/
cp .env.example .env             # případně uprav hesla
docker compose up -d             # nastartuje EMQX i TimescaleDB
```

Ověření:

| Co | Kde | Default |
|---|---|---|
| EMQX dashboard | http://localhost:18083 | `admin` / `iot-dev` (z `.env`) |
| MQTT TCP | `tcp://localhost:1883` | bez autentizace (Fáze 2) |
| MQTT WebSocket | `ws://localhost:8083/mqtt` | bez autentizace (Fáze 2) |
| TimescaleDB | `postgres://iot:iot-dev@localhost:5432/iot` | z `.env` |
| Grafana | http://localhost:3000 | `admin` / `iot-dev` (z `.env`) |
| Health check | `docker compose ps` | sloupec `STATUS` ukáže `healthy` |

Datasource TimescaleDB je v Grafaně **provisioned** automaticky (žádné klikání).
Ověření připojení:

```bash
curl -s -u admin:iot-dev \
  "http://localhost:3000/api/datasources/uid/$(curl -s -u admin:iot-dev \
   http://localhost:3000/api/datasources | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["uid"])')/health"
# → {"message":"Database Connection OK","status":"OK"}
```

Kontrola schématu DB:

```bash
docker exec iot-timescaledb psql -U iot -d iot -c '\dt'
docker exec iot-timescaledb psql -U iot -d iot \
  -c "SELECT hypertable_name FROM timescaledb_information.hypertables;"
```

Smoke test publish/subscribe — pokud máš lokálně `mosquitto-clients`:

```bash
mosquitto_sub -h localhost -t 'v1/dev/+/telemetry' &
mosquitto_pub -h localhost -t 'v1/dev/test/telemetry' -m '{"schema":"v1","ts":0,"seq":1,"measurements":[]}'
```

Bez lokálního klienta (přes kontejner na host síti):

```bash
docker run --rm --network host eclipse-mosquitto sh -c \
  'mosquitto_sub -h localhost -t "v1/dev/+/telemetry" -C 1 -W 10 & \
   sleep 1; mosquitto_pub -h localhost -t "v1/dev/test/telemetry" -m "{\"schema\":\"v1\",\"seq\":1}"; wait'
```

V EMQX dashboardu **Monitoring → Topics** se objeví `v1/dev/test/telemetry`.

## Porovnání MQTT brokerů

K dispozici je 7 brokerů, každý pod vlastním **docker-compose profilem**. Vždy
běží **jen jeden** (všechny mapují port 1883), takže simulátor i testy pořád míří
na `localhost:1883`. Slouží to k porovnání brokerů (bod 2 zadání) jako
**samostatný experiment** — oddělený od benchmarku backendových stacků (Fáze 3),
aby se neměnily dvě proměnné najednou.

| Broker | Profil | Jazyk / typ | MQTT | UI / extra |
|---|---|---|---|---|
| **EMQX** | `emqx` | Erlang, feature-rich | 1883 | dashboard 18083, WS 8083 |
| **Mosquitto** | `mosquitto` | C, lehký (referenční) | 1883 | WS 9001 |
| **NanoMQ** | `nanomq` | C/NNG, ultra-lehký edge | 1883 | HTTP API 8081 |
| **HiveMQ CE** | `hivemq` | Java, enterprise | 1883 | WS 8000 |
| **VerneMQ** | `vernemq` | Erlang, distribuovaný | 1883 | — |
| **RabbitMQ** | `rabbitmq` | AMQP + MQTT plugin | 1883 | management 15672 |
| **Artemis** | `artemis` | Java, multi-protokol | 1883 | console 8161 |

### Přepínání brokerů

Nejjednodušeji helper skriptem `./broker.sh` (zastaví vše + nahodí vybraný broker):

```bash
./broker.sh list              # vypíše dostupné brokery
./broker.sh mosquitto         # přepne na Mosquitto (+ platforma DB/Grafana)
./broker.sh nanomq --no-platform   # jen broker, bez DB/Grafany (lean benchmark)
./broker.sh down              # zastaví vše
```

> Dokud nemáš docker bez `sudo` (čerstvě přidaná skupina `docker`), spouštěj
> přes `sg docker -c './broker.sh emqx'`.

Ručně přes profily:

```bash
docker compose --profile '*' down                          # zastav vše
COMPOSE_PROFILES=platform,hivemq docker compose up -d       # nahoď HiveMQ + platformu
```

### Ověření brokeru

Každý broker se dá ověřit stejným pub/sub testem (nezávislým na typu brokeru):

```bash
docker run --rm --network host eclipse-mosquitto \
  timeout 6 mosquitto_sub -h localhost -t 'v1/dev/+/telemetry' -v &
cd ../simulator && .venv/bin/python -m simulator --devices 2 --count 3 --seed 1
```

Všech 7 brokerů je ověřeno: simulátor → broker → subscriber, 6/6 zpráv.

## Konfigurace

| Soubor | Co řeší |
|---|---|
| `docker-compose.yml` | služby (7 brokerů + platforma), profily, porty, volumy |
| `broker.sh` | přepínání aktivního brokeru |
| `timescale/init/*.sql` | schéma (§5), telemetrie hypertable, seed (běží při 1. startu) |
| `mosquitto/mosquitto.conf` | Mosquitto listener + anonymní přístup |
| `rabbitmq/{rabbitmq.conf,enabled_plugins}` | RabbitMQ MQTT plugin + listener |
| `.env` (lokální) | aktivní profily, dashboard/DB hesla (necommitované) |
| `.env.example` | šablona pro `.env` (commitovaná) |

EMQX se konfiguruje **přes proměnné prostředí** v `docker-compose.yml` (doporučený
postup pro Docker), ne přes vlastní `emqx.conf` — tím zůstanou zachované výchozí
listenery i dashboard. Anonymní připojení je ve Fázi 2 záměrně povolené.

Data brokeru/DB se ukládají do pojmenovaných Docker volumů (`emqx-data`,
`emqx-log`) — spravuje je Docker, v repu nejsou. Smazání: `docker compose down -v`.

## Co tady (ještě) **není**

- Per-device autentizace + ACL → Fáze 4 (TESTING.md bezpečnostní testy).
- Prometheus exporter + Grafana **dashboardy** → Fáze 5 (teď jen prázdná Grafana + datasource).
- Retention / downsampling v Timescale → Fáze 4.

> Init skripty (`timescale/init/*.sql`) běží **jen při prvním startu** (prázdný
> volume). Po změně schématu je nutný reset: `docker compose down -v`.
