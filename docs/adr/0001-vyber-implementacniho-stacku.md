# ADR 0001: Výběr implementačního stacku backendu

- **Stav:** Přijatý (rozhodnuto na základě benchmarku)
- **Datum:** 2026-06-10

## Kontext

Backend (ingestion + API) lze postavit v několika stacích. Místo dohadu volbu
opíráme o měření na sdílené infrastruktuře (stejný broker + DB + generátor zátěže).

## Zvažované varianty

- Python (FastAPI + asyncio-mqtt)
- C# / .NET (MQTTnet + EF Core)
- Node.js (NestJS + mqtt.js)
- Java / Spring Boot

## Kritéria

Throughput · latence (p50/p95/p99) · spotřeba zdrojů (CPU/RAM/image) ·
rychlost vývoje · zralost knihoven a znalost stacku.

## Naměřené výsledky

Každý kandidát = tenká kontejnerizovaná ingestion služba se **stejným kontraktem**
(MQTT subscribe → parse → dávkový COPY do TimescaleDB). Stejný broker (EMQX),
stejná DB, stejná zátěž (publisher), měřeno zvenčí (latence z DB = `received_at − time`,
CPU/RAM z cgroup). Kód a harness: [benchmarks/](../../benchmarks/), grafy v
`benchmarks/brokers/charts/stack-*.png`.

Při **5 000 zpráv/s** (medián ze 2 běhů):

| Stack | uloženo/s | p95 latence | CPU | RAM | strop (čistě) |
|---|---:|---:|---:|---:|---|
| **.NET (C#)** | 5 000 | **40 ms** | 70 % | **40 MB** | 10 000/s |
| Java / Spring | 5 000 | 43 ms | **33 %** | 187 MB | 10 000/s |
| Node.js | 5 000 | 107 ms | 34 % | 59 MB | ~5–6 000/s |
| Python | 5 000 | 4 172 ms ⚠️ | 65 % | 40 MB | ~2 500–3 000/s |

- **.NET a Java** uložily i 10 000/s s 0 % ztrát (nejvýkonnější).
- **Node** je solidní střed; **Python** saturuje nejdřív (~2 500/s — GIL + asyncio),
  při 5 000/s latence vyletí na ~4 s.
- Pozn.: úzké hrdlo je ingestion konzument (potvrzeno i broker-pipeline testem),
  takže rozdíly mezi jazyky se projeví přímo na end-to-end výkonu.

## Rozhodnutí

**.NET (C#)** — ASP.NET Core pro celý backend (ingestion + REST/WS API + EF Core).

Důvody:

1. **Nejvyrovnanější výkon** — propustnost na úrovni Javy (10 000/s, 0 ztrát),
   nejnižší latence (40 ms), a přitom **nejlehčí RAM (40 MB)** z výkonné dvojice.
2. **Vhodné na jeden host** — broker + DB + backend + Grafana běží společně, kde
   je paměťová stopa vidět víc než CPU; .NET má 40 MB vs 187–366 MB u Javy (Spring+JVM).
3. **Rychlý start a lehký image** (288 MB vs 452 MB Java) → příjemná vývojová smyčka.
4. **First-class na Windows** (cílový vývojový stroj) — ROADMAP §2 to uvádí jako plus.
5. **Cohezní stack na celý backend** — ASP.NET Core (REST + WebSocket) + EF Core
   (metadata) + Npgsql (telemetrie), MQTTnet pro broker.
6. Zapadá do **zkušenosti** s C-rodinou jazyků (kritérium „znalost stacku").

## Důsledky

- **Klad:** výkon (důležité — ingestion je hrdlo) + nízká stopa + jeden cohezní
  stack na celý backend.
- **Kompromis:** vyšší CPU než Java (při reálné zátěži s report-by-exception ale
  ani jeden nevytíží); nový jazyk oproti dosavadnímu Pythonu v repu (simulátor a
  benchmarky zůstanou v Pythonu — jsou to nástroje, ne produkční backend).
- **Zavržené:** Java/Spring (těžká RAM, pomalý start), Node (nižší propustnost —
  ale zvážit pro dashboard/WebSocket vrstvu ve Fázi 5), Python (nejslabší
  propustnost; zůstává jako jazyk simulátoru a benchmarků).
- Backend se postaví v `backend/` (ASP.NET Core); tenký ingestion prototyp z
  `benchmarks/dotnet/` je odrazový můstek.

## Reference

- Benchmark a metodika: [benchmarks/](../../benchmarks/)
- Souvisí s [ADR 0004](0004-vyber-mqtt-brokeru.md) (broker EMQX)
- Ověření proti literatuře (citace): [docs/reference/externi-zdroje.md](../reference/externi-zdroje.md)
  — naše pořadí (.NET ≈ Java > Node > Python) i paměťový rozdíl .NET vs Spring
  odpovídají publikovaným srovnáním.
