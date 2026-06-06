# infra/

Lokální vývojové a testovací prostředí (Docker).

Plánovaný obsah (Fáze 2 roadmapy):

- `docker-compose.yml` — MQTT broker (EMQX/Mosquitto) + time-series DB
  (TimescaleDB/InfluxDB) + Postgres (metadata) + Grafana.
- konfigurace brokeru (ACL, autentizace, listenery),
- init skripty DB (schéma, hypertables, retention).

> Lokální data DB se **necommitují** (viz `.gitignore`: `infra/data/`).
