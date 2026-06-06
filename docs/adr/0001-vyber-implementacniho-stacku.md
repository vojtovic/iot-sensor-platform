# ADR 0001: Výběr implementačního stacku backendu

- **Stav:** Navržený (rozhodnutí padne po benchmarku — viz TESTING.md §5)
- **Datum:** _doplň_

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

> Doplň tabulku z benchmarku (TESTING.md §5).

| Stack | Max msg/s | p95 latence | CPU | RAM | Dev effort |
|---|---|---|---|---|---|
| | | | | | |

## Rozhodnutí

> _Jaký stack a proč._

## Důsledky

> _Co z toho plyne (klady i kompromisy)._
