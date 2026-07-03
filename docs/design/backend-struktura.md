# Struktura backendu (Fáze 4)

Návrh členění a technického základu plného backendu v **.NET / C#**
(rozhodnuto [ADR 0001](../adr/0001-vyber-implementacniho-stacku.md)). Backend
pokrývá **body 4 a 7** zadání: ingestion, device registry + konfigurace,
REST/WebSocket API, autentizace. Staví se v `backend/`; tenký srovnávací prototyp
je `benchmarks/dotnet/` (odrazový můstek, ne produkční kód).

> **Stav:** návrh skeletonu. Skeleton (kostra, DI, připojení, 1 průchozí endpoint)
> staví Claude; vlastní doménovou logiku (validace, dedup, registry, API dotazy,
> WebSocket, auth) dopisuje autor. Cíl kostry: **buildne se a reálně se připojí**
> k běžícímu EMQX + TimescaleDB.

## Cíle a principy

- **Profesionální, obhajitelná struktura** — vrstvená (clean-ish) architektura,
  jasné hranice komponent, testovatelné jednotky.
- **Ingestion škáluje nezávisle na API** — přímý důsledek klíčového nálezu benchmarků
  (úzké hrdlo je ingestion konzument, ne broker/DB → víc replik ingestionu přes
  MQTT 5 shared subscriptions). Proto je ingestion **samostatně nasaditelná služba**,
  ne background vlákno v API procesu.
- **DB je zdroj pravdy** — schéma žije v `infra/timescale/init/*.sql` (a `telemetry`
  je hypertable). EF Core se na existující tabulky **mapuje ručně** (database-first),
  žádné code-first migrace přepisující SQL init.
- **Telemetrie mimo ORM** — vysoký zápisový tok jde přes Npgsql **binární COPY**
  (jak v prototypu), ne přes EF change-tracking.

## Členění řešení

```
backend/
├─ IoT.sln
├─ Directory.Build.props        # nullable enable, warnings-as-errors, LangVersion, analyzery
├─ .editorconfig                # jednotný styl kódu
├─ src/
│  ├─ IoT.Core/                 # doména, DTO, kontrakty; kanonický model měření
│  │                            #   (SenML-like: device_id, seq, ts, measurements[])
│  ├─ IoT.Infrastructure/       # EF Core DbContext (metadata) + Npgsql COPY (telemetrie)
│  │                            #   + MQTT klient (MQTTnet), konfigurace (Options pattern)
│  ├─ IoT.Ingestion/            # Worker Service: subscribe → validace → dedup → batch COPY
│  └─ IoT.Api/                  # ASP.NET Core: Controllers (REST /v1) + WebSocket + OpenAPI
├─ tests/
│  ├─ IoT.Core.Tests/           # xUnit — čisté funkce (validace, dedup, parsing payloadu)
│  └─ IoT.Api.Tests/            # integrační (WebApplicationFactory)
├─ Dockerfile.ingestion
└─ Dockerfile.api
```

Závislosti vrstev (jednosměrné): `Api`, `Ingestion` → `Infrastructure` → `Core`.
`Core` nezávisí na ničem (žádné EF/MQTT typy v doméně).

| Projekt | Odpovědnost | Klíčové balíčky |
|---|---|---|
| **IoT.Core** | doména, DTO, kontrakty, rozhraní (porty) | — (čistý C#) |
| **IoT.Infrastructure** | DbContext, Npgsql COPY, MQTT klient, config | Npgsql, EFCore.Npgsql, MQTTnet |
| **IoT.Ingestion** | příjem → validace → dedup → dávkový zápis | Microsoft.Extensions.Hosting |
| **IoT.Api** | REST + WS + OpenAPI, health checks | ASP.NET Core, Swashbuckle |

## Datový tok

```
EMQX ──MQTT 5 (shared sub)──> IoT.Ingestion ──binární COPY──> telemetry (hypertable)
                                    │                          metadata (channel map)
                                    └── validace + dedup (device_id+seq)
IoT.Api ── REST /v1 + WS ──> čte telemetrii (Npgsql) + metadata (EF Core)
```

## Rozhodnutá technická volba

- **API styl:** Controllers (`[ApiController]`) — klasický enterprise standard,
  verzované `/v1`, OpenAPI/Swagger.
- **Metadata:** EF Core, database-first, ruční mapování na existující tabulky.
- **Telemetrie:** Npgsql binární COPY (zápis), Npgsql dotazy (čtení).
- **MQTT:** MQTTnet, QoS 1, shared subscriptions (`$share/...`) pro škálování ingestionu.
- **Konfigurace:** Options pattern + `appsettings.json` + env override (ne ad-hoc `Env()`).
- **Logging:** structured logging; health checks na `/health`.
- **Testy:** xUnit.
- **CI:** zatím ne (přidá se později).

## Rozsah skeletonu vs. dopisovaná logika

**Skeleton (staví Claude, ověří `dotnet build` + reálné připojení):**
- Solution + 6 projektů + reference + `Directory.Build.props` + `.editorconfig`.
- DI kontejner, konfigurace (Options), structured logging, health checks.
- EF Core `DbContext` namapovaný na `tenant/site/location/device/channel`.
- Připojení k MQTT (MQTTnet) a DB (Npgsql) — ověřené, že naváže spojení.
- Jeden průchozí endpoint: `GET /v1/devices` (z metadat) + `GET /health`.
- Kostra ingestion workeru (subscribe + prázdné místo pro validaci/zápis).
- Dockerfily + zapojení do `infra/docker-compose.yml`.

**Dopisuje autor:**
- Schema validace telemetrie, dedup `device_id+seq`, backpressure/dávkování.
- Device registry + registrační flow (bod 7): reg/request → reg/response → config.
- API dotazy: telemetrie (rozsahy, agregace), detail/seznam zařízení, poslední hodnoty.
- WebSocket live stream.
- Autentizace: API klíče / JWT pro klienty, credentials + ACL pro zařízení.

## Reference (dokumentace k použitým technologiím)

Doplní se do [docs/reference/externi-zdroje.md](../reference/externi-zdroje.md)
při stavbě skeletonu (ASP.NET Core, EF Core keyless/table mapping, Npgsql COPY,
MQTTnet, Worker Service, health checks).
