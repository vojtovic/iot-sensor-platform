# infra/

Lokální vývojové a testovací prostředí (Docker).

## Stav

Postupuje se po krocích Fáze 2 (viz [ROADMAP](../ROADMAP.md#fáze-2--sdílená-infrastruktura-základ-pro-bod-4--1-týden)):

- [x] **MQTT broker (EMQX)** — dashboard, listenery 1883 / 8083 / 18083
- [ ] TimescaleDB (telemetrie + metadata, jeden Postgres engine)
- [ ] Grafana (provisioned datasource → Timescale)
- [ ] Init skripty schématu (`§5` modelu)

## Rychlý start

```bash
cd infra/
cp .env.example .env             # případně uprav hesla
docker compose up -d emqx
```

Ověření:

| Co | Kde | Default |
|---|---|---|
| EMQX dashboard | http://localhost:18083 | `admin` / `iot-dev` (z `.env`) |
| MQTT TCP | `tcp://localhost:1883` | bez autentizace (Fáze 2) |
| MQTT WebSocket | `ws://localhost:8083/mqtt` | bez autentizace (Fáze 2) |
| Health check | `docker compose ps` | sloupec `STATUS` ukáže `healthy` |

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

## Konfigurace

| Soubor | Co řeší |
|---|---|
| `docker-compose.yml` | služby, porty, volumy, healthcheck |
| `.env` (lokální) | dashboard heslo apod. (necommitované) |
| `.env.example` | šablona pro `.env` (commitovaná) |

EMQX se konfiguruje **přes proměnné prostředí** v `docker-compose.yml` (doporučený
postup pro Docker), ne přes vlastní `emqx.conf` — tím zůstanou zachované výchozí
listenery i dashboard. Anonymní připojení je ve Fázi 2 záměrně povolené.

Data brokeru/DB se ukládají do pojmenovaných Docker volumů (`emqx-data`,
`emqx-log`) — spravuje je Docker, v repu nejsou. Smazání: `docker compose down -v`.

## Co tady (ještě) **není**

- Per-device autentizace + ACL → Fáze 4 (TESTING.md bezpečnostní testy).
- Prometheus exporter + Grafana dashboardy → Fáze 5.
- Retention / downsampling v Timescale → Fáze 4.
