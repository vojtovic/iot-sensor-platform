# Průvodce implementací backendu (Fáze 4)

> **Formát:** roadmapa/checklist **pro autora** — píšeš kód sám. Každý task říká
> _co_ postavit, _kde_, _kdy je hotovo_ a _kam se podívat do dokumentace_. Záměrně
> **neobsahuje hotový kód** (to je tvoje práce). Vychází z návrhu
> [backend-struktura.md](backend-struktura.md) a ROADMAP §4 (Fáze 4).

**Cíl fáze (Definition of done, ROADMAP §4):** simulátor → broker → ingestion → DB
→ API vrátí stejná data. K tomu ingestion s validací/dedup, device registry +
registrace/konfigurace (bod 7), REST + WebSocket API, autentizace, retence/downsampling.

**Výchozí bod:** holá kostra v `backend/` (solution `IoT.slnx`, 6 projektů, build
config, NuGet závislosti). Projekty jsou prázdné.

## Globální pravidla (platí pro každý task)

- **net10.0**, `Nullable enable`, `TreatWarningsAsErrors true` (kód musí být bez varování).
- **DB je zdroj pravdy** — schéma je v `infra/timescale/init/*.sql`. **Negeneruj EF
  migrace**, které by ho přepsaly; EF mapuj ručně na existující tabulky.
- **Telemetrie jde mimo EF** — vysoký zápisový tok přes Npgsql **binární COPY**, ne
  EF change-tracking. Metadata (zařízení, kanály, config) přes EF Core.
- **Dedup `(device_id, seq)` řeší ingestion vrstva**, ne unikátní index (TimescaleDB
  vyžaduje v unique indexu partitioning sloupec `time` — to by dedup rozbilo).
- **Commity česky**, prefix `Fáze 4:`, tělo + řádek `Ověřeno:` s důkazem (co se spustilo).
- **Ověřuj spuštěním** — nahoď infra (`cd infra && docker compose up -d`), udělej
  MQTT round-trip / DB dotaz, než řekneš „hotovo".
- **Prostředí:** spuštění API/ingestionu i integrační testy vyžadují ASP.NET Core
  runtime — `sudo pacman -S aspnet-runtime` (teď je jen .NET runtime). Docker případně
  přes `sg docker -c '...'`.
- **Dokumentace ke stacku:** [docs/reference/externi-zdroje.md](../reference/externi-zdroje.md)
  (sekce „Backend implementace") — u každého tasku níže jsou i konkrétní odkazy.

**Doporučené pořadí:** 1 → 11. Každý task je samostatně ověřitelný; klidně dělej po
jednom commitu. Můžeš přeskládat, ale 1–4 tvoří základ pro zbytek.

---

## Task 1 — Doménový model + parser (`IoT.Core`)

**Cíl:** kanonický model telemetrie a čistá funkce parse+validace payloadu.

**Soubory:** `src/IoT.Core/Telemetry/*.cs` (např. `TelemetryPayload`, `Measurement`,
`TelemetryRow`), `src/IoT.Core/Abstractions/ITelemetryWriter.cs`. Testy v
`tests/IoT.Core.Tests/`.

**Co postavit:**
- DTO kanonického payloadu dle ROADMAP §6: `{schema, device_id, ts, seq, measurements:[{ch,v,u}], meta}`.
- `TelemetryRow` (řádek pro DB): `time, device_id, channel_id (long/bigint!), value, quality (short), seq`.
- Parser JSON→DTO + **business validace** (povinná pole, `seq >= 0`, známé kanály, rozsahy).
- Port `ITelemetryWriter.WriteAsync(IReadOnlyList<TelemetryRow>, CancellationToken)`.
- Pomůcka pro dedup (viz úskalí) — např. čistá funkce, která z proudu zpráv odfiltruje
  už viděné `(device_id, seq)`.

**Hotovo, když:** `dotnet test tests/IoT.Core.Tests` projde — testy pokrývají validní
payload, chybné vstupy a dedup logiku (čisté funkce, bez brokeru/DB).

**Dokumentace:** System.Text.Json (parsování), xUnit. Viz externi-zdroje.

**Úskalí:** `channel_id` je v DB **bigint (int8)** → v C# `long`, ne `int`. Dedup drž
v ingestion vrstvě (Task 5), tady jen čistá logika.

---

## Task 2 — EF Core metadata (`IoT.Infrastructure`)

**Cíl:** číst/zapisovat relační metadata (hierarchie zařízení) přes EF Core, mapované
na existující schéma.

**Soubory:** `src/IoT.Infrastructure/Metadata/*.cs` (entity + `AppDbContext`).

**Co postavit:**
- Entity pro `tenant, site, location, device, channel` (podle
  `infra/timescale/init/01_metadata.sql` — názvy sloupců musí sedět).
- `AppDbContext` s **fluent API** mapováním (`ToTable`, `HasColumnName`, klíče,
  `ValueGeneratedOnAdd` pro identity sloupce, vztahy).

**Hotovo, když:** proti běžící TimescaleDB umíš načíst zařízení (seed má `esp32-sim-001/002`)
— ověř malým integračním testem nebo dočasným dotazem. Build bez varování.

**Dokumentace:** EF Core modeling (fluent API), scaffolding (kdybys chtěl DbContext
vygenerovat z DB a pak upravit), Npgsql EF Core provider. Viz externi-zdroje.

**Úskalí:** nemapuj sloupce, které nepotřebuješ (např. `channel.calibration jsonb`) —
EF nevadí neúplné mapování. Žádné `Add-Migration`/`dotnet ef migrations` proti tomuto
schématu.

---

## Task 3 — Zápis telemetrie: Npgsql COPY + mapa kanálů

**Cíl:** produkční `ITelemetryWriter` binárním COPY a načtení mapy `(device_id, quantity) → channel_id`.

**Soubory:** `src/IoT.Infrastructure/Telemetry/*.cs`.

**Co postavit:**
- Implementace `ITelemetryWriter` přes `NpgsqlDataSource` + `BeginBinaryImportAsync`
  do `COPY telemetry (time, device_id, channel_id, value, quality, seq) FROM STDIN (FORMAT BINARY)`.
  Vzor je v prototypu `benchmarks/dotnet/Program.cs`.
- Načtení mapy kanálů (jednorázově, `SELECT id, device_id, quantity FROM channel`) —
  ingestion podle ní překládá `ch` → `channel_id`.

**Hotovo, když:** integrační test zapíše dávku řádků a přečte je zpět z `telemetry`
(proti běžící DB). `received_at` doplní default DB, `time` = čas měření.

**Dokumentace:** Npgsql — Binary COPY, NpgsqlDataSource, typy. Viz externi-zdroje.

**Úskalí:** typy v `WriteAsync` musí přesně sedět (`NpgsqlDbType.Bigint` pro `channel_id`
a `seq`, `Smallint` pro `quality`, `TimestampTz` pro `time`) — jinak „insufficient data"
chyba. Jedno spojení nesmí dělat víc COPY naráz (serializuj zápis, např. přes frontu).

---

## Task 4 — DI + konfigurace (`AddInfrastructure`)

**Cíl:** jedno místo, které zaregistruje DbContext, Npgsql datasource, writer a options.

**Soubory:** `src/IoT.Infrastructure/DependencyInjection.cs`, `MqttOptions.cs`,
`appsettings.json` v `IoT.Api` a `IoT.Ingestion`.

**Co postavit:**
- `AddInfrastructure(IServiceCollection, IConfiguration)`: `AddDbContext<AppDbContext>(UseNpgsql(...))`,
  singleton `NpgsqlDataSource`, `ITelemetryWriter`, `Configure<MqttOptions>(...)`.
- `MqttOptions` (Options pattern): host, port, topic (shared subscription!), qos, clientId.
- Connection string `Timescale` + sekce `Mqtt` v obou `appsettings.json`.

**Hotovo, když:** oba hostitelské projekty (`IoT.Api`, `IoT.Ingestion`) se sestaví a
`AddInfrastructure` zaregistruje služby bez chyby (ověř např. `builder.Build()` bez výjimky).

**Dokumentace:** Options pattern, Configuration, Dependency injection. Viz externi-zdroje.

**Úskalí:** v kontejneru se broker/DB adresují jmény služeb (`emqx`, `timescaledb`),
lokálně `localhost`. Nedávej hesla natvrdo do kódu — do appsettings/env.

---

## Task 5 — Ingestion worker (`IoT.Ingestion`)

**Cíl:** srdce pipeline — příjem MQTT → parse → validace → dedup → dávkový zápis.

**Soubory:** `src/IoT.Ingestion/Program.cs`, `IngestionWorker.cs` (BackgroundService).

**Co postavit:**
- MQTTnet klient: connect na EMQX, subscribe na **shared subscription**
  `$share/ingest/v1/dev/+/telemetry` (QoS 1) → víc replik = load-balancing.
- Na zprávě: parse (Task 1) → validace → překlad kanálů (Task 3 mapa) → dedup
  `(device_id, seq)` → dávkování (velikost / časový flush) → `ITelemetryWriter.WriteAsync`.
- Ošetření chyb (poškozená zpráva se zahodí, ne shodí službu) a backpressure (fronta).

**Hotovo, když (DoD milník):** pustíš simulátor (`cd simulator && python -m simulator
--devices 2 --rate 1`), a v `telemetry` přibývají řádky odpovídající poslaným zprávám
(žádné duplicity při replay). Ověř `SELECT count(*)` a pár hodnot.

**Dokumentace:** Worker Services / BackgroundService, MQTTnet (wiki + samples), MQTT
shared subscriptions. Viz externi-zdroje.

**Úskalí:** MQTTnet doručuje zprávy na vlastních vláknech — zápis serializuj (fronta +
jeden konzument). Dedup drž v paměti per-device (poslední `seq`) + rozumné okno pro replay.
Šarže + časový flush, ať nezdržuješ poslední neúplnou dávku.

---

## Task 6 — REST API + health + OpenAPI (`IoT.Api`)

**Cíl:** číst data ven — zařízení a telemetrie — a mít zdravotní/dokumentační endpointy.

**Soubory:** `src/IoT.Api/Program.cs`, `Controllers/*.cs`.

**Co postavit:**
- `Program.cs`: `AddInfrastructure`, `AddControllers`, `AddOpenApi`, health check nad
  `AppDbContext` (`AddDbContextCheck`), `MapControllers`, `MapOpenApi`, `MapHealthChecks("/health")`.
- Controllery (verzované `/v1`): seznam/detail zařízení (EF); telemetrie — časové
  rozsahy, poslední hodnoty, agregace (Npgsql dotazy nad `telemetry`).

**Hotovo, když (DoD milník):** `curl /health` = Healthy; `curl /v1/devices` vrátí
zařízení z DB; dotaz na telemetrii vrátí data, která poslal simulátor (shoda s DB).

**Dokumentace:** ASP.NET Core Web API (Controllers), routing, OpenAPI (built-in),
Health checks. Viz externi-zdroje.

**Úskalí:** dotazy na telemetrii jsou time-series — filtruj přes `time` (index
`(channel_id, time DESC)`), pro „poslední hodnotu" zvaž `SELECT DISTINCT ON` /
Timescale `last()`. Odděl výstupní DTO od EF entit.

---

## Task 7 — WebSocket live stream (`IoT.Api`)

**Cíl:** živý přenos telemetrie do klienta/dashboardu.

**Soubory:** `src/IoT.Api/` (WS endpoint + broadcast).

**Co postavit:**
- WebSocket endpoint (`UseWebSockets`, accept), který posílá klientovi příchozí
  telemetrii (např. API si drží vlastní MQTT subscribe, nebo interní pub/sub z ingestionu).
- Jednoduchý broadcast více klientům; filtr podle zařízení/kanálu volitelně.

**Hotovo, když:** připojený WS klient dostává živé zprávy, zatímco běží simulátor.

**Dokumentace:** ASP.NET Core WebSockets. Viz externi-zdroje.

**Úskalí:** WS na API vrstvě neškáluj přes shared subscription se stejným group name
jako ingestion (jinak si „ukradnou" zprávy) — použij vlastní (ne-shared) subscribe nebo
samostatnou skupinu.

---

## Task 8 — Device registry + registrace/konfigurace (bod 7)

**Cíl:** zařízení se umí zaregistrovat a dostat konfiguraci (ROADMAP §7).

**Soubory:** `src/IoT.Infrastructure/Metadata/` (config/capabilities entity),
`src/IoT.Api/` nebo `src/IoT.Ingestion/` (handler registračního flow).

**Co postavit:**
- Handler `reg/request` (`v1/dev/{id}/reg/request`): ověř provisioning token, vytvoř/najdi
  `device` + `channel`y, vydej identitu → `reg/response`, publikuj **retained** `config`.
- Verzování konfigurace (`device_config`, `config_version`); zařízení potvrdí verzi ve
  `status`/`ack`.
- REST správa: seznam/registrace zařízení, čtení/zápis konfigurace.

**Hotovo, když:** simulace registračního flow (pošli `reg/request`) → v DB vznikne
zařízení + kanály, přijde `reg/response` a retained `config`.

**Dokumentace:** ROADMAP §7, [ADR 0002](../adr/0002-vynuceni-ukladaci-politiky.md)
(ukládací politika), MQTTnet (retained/publish). Viz externi-zdroje.

**Úskalí:** příkaz = jednorázová akce (neretained), konfigurace = žádaný stav (retained
`config` topic, „device shadow"). Provisioning token drž bezpečně (hash), ne plaintext.

---

## Task 9 — Autentizace (klienti + zařízení)

**Cíl:** chránit API a broker.

**Soubory:** `src/IoT.Api/` (auth pipeline), `infra/` (EMQX ACL/credentials).

**Co postavit:**
- API: API klíče / JWT pro klienty (`AddAuthentication`/`AddJwtBearer`, `[Authorize]`),
  případně tabulka `api_key` (hash) z metadat.
- Broker: per-device credentials + **ACL** na EMQX (zařízení smí jen své topiky
  `v1/dev/{id}/#`).

**Hotovo, když:** neautorizovaný request na chráněný endpoint = 401; zařízení bez práv
nepublikuje do cizího topiku.

**Dokumentace:** ASP.NET Core Authentication, JWT bearer, Authorization; EMQX
authn/authz (ACL) — doplň do externi-zdroje při rešerši.

**Úskalí:** hesla/klíče nikdy plaintextem (hash + salt). EMQX ACL se konfiguruje přes
env/plugin, ne přepisem `emqx.conf` (rozbil by listenery — viz CLAUDE.md).

---

## Task 10 — Retence a downsampling (TimescaleDB)

**Cíl:** neuchovávat surová data donekonečna; rychlé agregace pro dashboard.

**Soubory:** `infra/timescale/init/` (nový SQL) nebo migrace přes API/skript.

**Co postavit:**
- **Continuous aggregate** (materializovaný pohled) pro downsampling (např. 1min/1h
  průměry per kanál) + refresh policy.
- **Retention policy** (`add_retention_policy`) na surové `telemetry`.
- Zvaž „report by exception" ukládací politiku (ADR 0002) v ingestionu (deadband +
  heartbeat) — omezí objem už při zápisu.

**Hotovo, když:** agregační pohled vrací downsamplovaná data; retenční politika je
nastavená (ověř `SELECT` nad agregátem a `timescaledb_information.jobs`).

**Dokumentace:** TimescaleDB — hypertables, continuous aggregates, data retention. Viz
externi-zdroje.

**Úskalí:** init SQL běží jen na prázdném volume — po změně schématu buď migrace, nebo
`docker compose down -v` (smaže data). Continuous aggregate nejde nad tabulkou bez
hypertable — `telemetry` jí je.

---

## Task 11 — E2E ověření, Docker, dokumentace

**Cíl:** uzavřít Fázi 4 — prokázat DoD a zabalit.

**Soubory:** `backend/Dockerfile.api`, `backend/Dockerfile.ingestion`,
`infra/docker-compose.yml` (profil `backend`), `backend/README.md`,
`docs/adr/` (případný ADR k API/auth), `docs/reference/externi-zdroje.md`.

**Co postavit:**
- Multi-stage Dockerfily (net10 SDK → aspnet/runtime) pro Api a Ingestion; služby pod
  profilem `backend` v compose (adresují `timescaledb`/`emqx`).
- README backendu: jak spustit, struktura, endpointy.
- Doplnit zdroje/ADR podle toho, co jsi rozhodl.

**Hotovo, když (Definition of done Fáze 4):** `docker compose --profile ...,backend up`
nahodí vše; simulátor → broker → ingestion → DB → **API vrátí stejná data**, co
simulátor poslal. WS ukazuje živá data. Ověřeno round-tripem.

**Dokumentace:** ASP.NET Core integrační testy (E2E), Docker. Viz externi-zdroje.

**Úskalí:** v compose `down` respektuje aktivní profily (`--profile '*' down` shodí i
neaktivní). Ingestion škáluj víc replikami (shared subscription) — ověř, že se dělí o zátěž.

---

## Průběžně

- **Testy:** čisté funkce (parse/validace/dedup) unit testy v `IoT.Core.Tests`; API
  smoke/integrační v `IoT.Api.Tests` (WebApplicationFactory, DB přes InMemory nebo
  testovací kontejner).
- **Mapování bodů zadání:** bod 4 (Task 5,6,7,10,11), bod 7 (Task 8,9). Pro text práce
  se hodí kapitola „Implementace backendu" + OpenAPI + sekvenční diagram registrace.
- **Když se zasekneš:** design [backend-struktura.md](backend-struktura.md), starší
  code-kompletní plán `docs/superpowers/plans/2026-07-03-backend-skeleton.md` (má i
  ukázkový kód parseru/EF/COPY), prototyp `benchmarks/dotnet/`.
