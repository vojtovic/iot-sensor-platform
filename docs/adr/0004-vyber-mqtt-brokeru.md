# ADR 0004: Výběr MQTT brokeru

- **Stav:** Přijatý (rozhodnuto na základě vlastního benchmarku)
- **Datum:** 2026-06-09

## Kontext

MQTT broker je páteř komunikace celé platformy (bod 2 zadání). Volbu jsme opřeli
o **vlastní benchmark 7 brokerů** na sdílené infrastruktuře — metodika, data a
grafy v [benchmarks/brokers/](../../benchmarks/brokers/README.md). Měřeno bylo
5 dimenzí: výkon (propustnost/latence/CPU/RAM, QoS 0/1), spolehlivost při výpadku,
škálovatelnost počtu spojení a end-to-end pipeline až do TimescaleDB.

Klíčové požadavky projektu: **škálovatelnost** (stovky–tisíce zařízení),
**spolehlivost** („0 ztrát") a featury pro platformu (monitoring, řízení).

## Zvažované varianty

EMQX 5.8 · Mosquitto 2 · NanoMQ 0.22 · HiveMQ CE 2024.3 · VerneMQ 1.13 ·
RabbitMQ 3.13 (MQTT plugin) · ActiveMQ Artemis 2.37.

## Naměřené výsledky (shrnutí, 5 000 zpráv/s, QoS 1)

| Broker | latence p99 | RAM | škálování spojení | přežije restart | shared subs / dashboard |
|---|---:|---:|---|---|---|
| **EMQX** | 57 ms | 249 MB | **10k čistě** | ano (s durable sessions) | **ano / ano** |
| Mosquitto | 12 ms | 11 MB | single-thread strop | ne (default) | ne / ne |
| NanoMQ | 15 ms | 8 MB | 10k čistě | ne (v0.22) | částečně / ne |
| VerneMQ | 32 ms | 376 MB | tisíce | ano | ano / slabší |
| HiveMQ CE | 865 ms* | 603 MB | slabší | ano | jen placené clustering |
| RabbitMQ | 488 ms | 268 MB | tisíce | ano | MQTT není priorita |
| Artemis | 18 ms | 674 MB | **selhává (~1k)** | ano | MQTT okrajově |

\* HiveMQ CE má QoS1 strop ~1 250/s (durabilní persistence).

Pipeline (end-to-end → DB): strop ~5 000/s je dán **ingestion vrstvou, ne brokerem**
(potvrzeno napříč 6 brokery; výjimka HiveMQ ~1 250/s).

## Rozhodnutí

**EMQX 5** jako centrální broker platformy, s **durable sessions** zapnutými
(`EMQX_DURABLE_SESSIONS__ENABLE=true` + `cluster.discovery_strategy=singleton`).

Důvody:

1. **Škálovatelnost** — čistě 10 000 spojení v testu (dle EMQ miliony); single
   uzel zvládne cílové stovky–tisíce zařízení bez přepisu.
2. **Featury pro platformu** — dashboard a Prometheus metriky (Fáze 5 monitoring),
   ACL, MQTT 5 **shared subscriptions** — ty přímo řeší hrdlo, které odhalil
   pipeline benchmark (škálování ingestionu víc konzumenty).
3. **Durabilita ověřena empiricky** — výchozí EMQX po restartu ztratil všech 500
   zpráv; **s durable sessions přežil restart s 0 ztrát** (ověřeno `failtest`,
   stejně jako HiveMQ/VerneMQ).

## Důsledky

- **Klad:** jedno řešení splňuje škálovatelnost + featury + durabilitu; „0 ztrát"
  je navíc kryto QoS 1 + durabilním zápisem do TimescaleDB (ověřeno pipeline testem).
- **Kompromis — výkon:** EMQX má vyšší CPU/latenci než lehké brokery (Mosquitto,
  NanoMQ); durable sessions navíc propustnost snižují (zápis na disk). Při cílové
  zátěži je to bezproblémové (hrdlem je stejně ingestion vrstva ~5 000/s), ale je
  to vědomý kompromis výkon ↔ featury+durabilita.
- **Mosquitto** zůstává jako lehká alternativa / edge broker a referenční bod.
- **Provoz:** singleton discovery = jednouzlové nasazení (clustering EMQX je
  navazující, pokud bude potřeba HA).
- Durabilita je v `docker-compose.yml` **přepínatelná** (`EMQX_DURABLE`), default
  vypnutá kvůli neměnnému chování benchmarků.

## Reference

- Benchmark: [benchmarks/brokers/README.md](../../benchmarks/brokers/README.md)
- Doporučení stacku: ROADMAP §9 (EMQX jako default)
- Ověření proti literatuře (citace): [docs/reference/externi-zdroje.md](../reference/externi-zdroje.md)
  — naše závěry (lehké brokery úsporné, EMQX škáluje, Mosquitto default bez
  persistence, NanoMQ 0.22 bez offline fronty) odpovídají zdrojům.
