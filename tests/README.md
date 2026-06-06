# tests/

Testy podle strategie v [../TESTING.md](../TESTING.md).

Úrovně:

- **unit** — parsování, validace, mapování, topic logika, dedup (`seq`),
- **integration** — reálný broker + DB (testcontainers): publish → ingest → query,
- **contract** — validace payloadů proti JSON Schema, verzování protokolu,
- **api** — REST/WS endpointy, auth,
- **e2e** — celý řetězec simulátor → broker → ingestion → DB → API,
- **load** — zátěž / škálovatelnost (rampa zařízení),
- **fault** — výpadky brokeru / ingestionu / DB / sítě, důkaz 0 ztracených zpráv.

> Klíčový test spolehlivosti: pošli N zpráv se sekvenčním `seq`, vyvolej výpadek →
> v DB musí být N unikátních `seq` bez mezer a bez duplikátů.
