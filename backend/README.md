# backend/

Plná implementace backendu ve **vítězném** stacku (po benchmarku).

Komponenty (Fáze 4 roadmapy):

- **ingestion** — subscribe na MQTT, schema validace, deduplikace (`device_id`+`seq`),
  dávkový zápis do DB,
- **device registry** — registrace, identifikace, konfigurace jednotek (bod 7),
- **API** — REST (dotazy na telemetrii, zařízení) + WebSocket (live data),
- **auth** — API klíče / JWT pro klienty, credentials + ACL pro zařízení.

> Tenké srovnávací prototypy kandidátů jsou v `../benchmarks/`, ne tady.
