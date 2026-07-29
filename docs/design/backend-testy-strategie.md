# Testovací strategie backendu (Fáze 4) — safety-net

> **Laťka:** praktický safety-net při psaní (ne plná důkazní sada). Cíl: jistota, že
> to co píšeš funguje, s minimem času. Doplňuje [TESTING.md](../../TESTING.md)
> (celková strategie) a [backend-implementace-pruvodce.md](backend-implementace-pruvodce.md)
> (tasky 1→11). Testy **píše autor**; tento dokument je jen mapa co/jak.

## Princip

Backend nemá zatím žádné testy (projekty `IoT.Core.Tests`, `IoT.Api.Tests` jsou
prázdné). Píšeme je **průběžně** s kódem (levnější než retrofit), na úrovni, která
kryje **rizika našeho use case**: 0 ztrát, 0 duplikátů (dedup), správné hodnoty,
odmítnutí nevalidních zpráv.

## Tři vrstvy

1. **Unit (rychlé, bez I/O)** — jádro, 80 % hodnoty. Čisté funkce:
   parse payloadu, validace, **dedup `(device_id, seq)`** + detekce mezery v `seq`,
   mapování kanálů, parsování topiců, rozhodovací logika ukládací politiky
   (deadband/hystereze/heartbeat), transformace „zpráva → řádky" ingestionu.
   → projekt `IoT.Core.Tests` (xUnit).

2. **Integrační (Testcontainers TimescaleDB)** — reálný průtok:
   COPY zapisovač zapíše→přečte, EF dotazy proti reálnému schématu, API endpointy
   vrátí správná data, dotaz nad continuous aggregate.
   → projekt `IoT.Api.Tests` (xUnit + Testcontainers + WebApplicationFactory).

3. **E2E smoke (1×, on-demand)** — simulátor→broker→ingestion→DB→API vrátí stejná
   data. Zároveň **důkaz Definition of done Fáze 4**. Ruční/on-demand proti
   `docker compose` (broker v smyčce necháváme mimo automat kvůli flakiness).

**Mimo rozsah testů (= experimenty, ne testy):** zátěž (§6), fault injection (§7),
latence (§8) z TESTING.md se **nepíšou** — spustí se existující `brokerbench`
(benchmarks/brokers/) proti backendu, čísla jdou do práce.

## Struktura a nástroje (minimum projektů)

| Projekt | Role | Nástroje |
|---|---|---|
| `IoT.Core.Tests` | unit (čisté funkce) | xUnit |
| `IoT.Api.Tests` | integrační (DB + API) | xUnit + Testcontainers for .NET (`Testcontainers.PostgreSql`, image `timescale/timescaledb`) + WebApplicationFactory |

- **Jeden Timescale kontejner na běh** (xUnit *collection fixture* — rychlé),
  inicializovaný **tvými `infra/timescale/init/01_metadata.sql` + `02_telemetry.sql`**
  → schéma zůstává single-source-of-truth (seed `03` netřeba, testy si píšou vlastní data).
- API běží přes `WebApplicationFactory` s connection stringem mířícím na kontejner
  (přepiš konfiguraci v test hostu). Infrastructure (COPY, EF) se testuje přímo proti
  stejnému kontejneru.
- **Izolace:** testy si volí vlastní `device_id`/`seq`, ať se nemíchají; případně
  truncate mezi testy. Balíček `Microsoft.EntityFrameworkCore.InMemory` už nebude
  potřeba (jedeme reálnou Timescale) — můžeš ho z `IoT.Api.Tests` odebrat.

## Vetkání k taskům (píšeš průběžně)

| Task (průvodce) | Typ | Co ověřit |
|---|---|---|
| 1 Doménový model + parser | unit | valid/malformed payload, validace, **dedup**, mapování kanálů |
| 2 EF metadata | integ. | dotaz na `device/channel` proti reálnému schématu |
| 3 COPY writer | integ. | zapiš dávku → přečti zpět (0 ztrát, správné hodnoty/typy) |
| 5 Ingestion | unit + smoke | „zpráva→řádky" + dedup; E2E až Task 11 |
| 6 REST API | integ. | `/v1/devices`, dotaz telemetrie, chybové kódy 400/404 |
| 8 Registry | integ. | reg flow → vznikne device+channel v DB |
| 9 Auth | integ. | bez tokenu 401 / cizí 403 |
| 10 Retence/agregace | integ. | dotaz nad continuous aggregate vrací downsampled data |
| 11 E2E | smoke | simulátor→…→API stejná data (DoD) |

## Akceptační kritéria (lehká, z TESTING.md §12)

- Integrační round-trip: **0 ztrát, 0 duplikátů**, uložená hodnota == odeslaná.
- Nevalidní payload: **nezapíše se, ale zaloguje** (ne tiše zahozen).
- API: správná data + správné chybové kódy (400/404/401).

## Prostředí

- **Testcontainers potřebuje Docker** při běhu testů (přes `sg docker` pokud nejsi ve
  skupině `docker`).
- **API + integrační testy vyžadují ASP.NET Core runtime** — `sudo pacman -S aspnet-runtime`
  (teď je jen .NET runtime).
- **CI (později):** unit na každý push (rychlé, bez infry); integrační (Testcontainers)
  nightly/on-demand. CI zatím není nastavené — viz TESTING.md §13.

## Dokumentace k nástrojům

- Testcontainers for .NET: https://dotnet.testcontainers.org/
- xUnit: https://xunit.net/docs/getting-started/v2/getting-started
- WebApplicationFactory (integrační testy): https://learn.microsoft.com/aspnet/core/test/integration-tests
- Doplněno v [docs/reference/externi-zdroje.md](../reference/externi-zdroje.md).
