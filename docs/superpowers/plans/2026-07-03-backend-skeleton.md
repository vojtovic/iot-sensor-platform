# Backend skeleton (Fáze 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Postavit ověřenou, profesionální kostru .NET backendu v `backend/` — buildne se, projdou testy a reálně se připojí k běžícímu EMQX + TimescaleDB; doménovou logiku (validace, dedup, registry, API dotazy, WS, auth) dopisuje autor.

**Architecture:** Vrstvené řešení dle [docs/design/backend-struktura.md](../../design/backend-struktura.md): `IoT.Core` (doména/DTO/kontrakty) ← `IoT.Infrastructure` (EF Core metadata + Npgsql COPY telemetrie + MQTT) ← `IoT.Ingestion` (Worker Service) a `IoT.Api` (ASP.NET Core Controllers + OpenAPI + health). Ingestion je samostatně nasaditelná služba (nezávislé škálování přes MQTT shared subscriptions). DB je zdroj pravdy — EF Core se mapuje database-first na existující schéma z `infra/timescale/init/*.sql`.

**Tech Stack:** .NET 10 (net10.0), C#; ASP.NET Core (Controllers), EF Core 10 + Npgsql.EntityFrameworkCore.PostgreSQL, Npgsql (binární COPY), MQTTnet 4.3, xUnit, built-in OpenAPI, Docker.

**Aktualizace rozsahu (holá kostra — rozhodnuto 2026-07-03):** stavíme jen **typy + propojení (wiring)**, funkční těla zůstávají jako `TODO (autor)`. Konkrétně jsou stubem: `TelemetryPayloadParser.Parse` (Task 2), `NpgsqlTelemetryWriter.WriteAsync` (Task 4) a dotaz v `GET /v1/devices` (Task 5). Reálné připojení k DB ověří **health-check** (otevře spojení), takže kostra jde spustit i bez doménové logiky. Testy netestují (neexistující) doménovou logiku — Core test je skip placeholder, Api test je boot/wiring smoke.

**Předpoklady prostředí:**
- `dotnet --version` → 10.0.x (ověřeno 10.0.104).
- Docker přes `sg docker -c '...'` (uživatel nemusí být v `docker` skupině — viz CLAUDE.md).
- Infrastruktura běží: `cd infra && sg docker -c 'docker compose up -d'` (profil `platform,emqx` → TimescaleDB na :5432, EMQX na :1883). Přihlašovací údaje DB: `iot / iot-dev`, databáze `iot` (viz `infra/.env.example` / compose).

---

## Struktura souborů (co vznikne)

```
backend/
├─ IoT.sln
├─ Directory.Build.props
├─ .editorconfig
├─ src/
│  ├─ IoT.Core/
│  │  ├─ IoT.Core.csproj
│  │  ├─ Telemetry/TelemetryPayload.cs       # kanonický DTO (ROADMAP §6) + measurement
│  │  ├─ Telemetry/TelemetryPayloadParser.cs # JSON → DTO (plumbing; validaci píše autor)
│  │  ├─ Telemetry/TelemetryRow.cs           # řádek pro zápis do DB
│  │  └─ Abstractions/ITelemetryWriter.cs    # port pro zápis telemetrie
│  ├─ IoT.Infrastructure/
│  │  ├─ IoT.Infrastructure.csproj
│  │  ├─ Metadata/AppDbContext.cs            # EF Core, mapování na existující tabulky
│  │  ├─ Metadata/Entities.cs                # Tenant/Site/Location/Device/Channel
│  │  ├─ Telemetry/NpgsqlTelemetryWriter.cs  # binární COPY do telemetry
│  │  ├─ Mqtt/MqttOptions.cs                 # konfigurace MQTT (Options pattern)
│  │  └─ DependencyInjection.cs              # AddInfrastructure(config)
│  ├─ IoT.Ingestion/
│  │  ├─ IoT.Ingestion.csproj
│  │  ├─ Program.cs                          # Host + AddInfrastructure + IngestionWorker
│  │  ├─ IngestionWorker.cs                  # subscribe → (TODO parse/validace/zápis)
│  │  └─ appsettings.json
│  └─ IoT.Api/
│     ├─ IoT.Api.csproj
│     ├─ Program.cs                          # DI, OpenAPI, health, controllers
│     ├─ Controllers/DevicesController.cs    # GET /v1/devices
│     └─ appsettings.json
├─ tests/
│  ├─ IoT.Core.Tests/
│  │  ├─ IoT.Core.Tests.csproj
│  │  └─ TelemetryPayloadParserTests.cs
│  └─ IoT.Api.Tests/
│     ├─ IoT.Api.Tests.csproj
│     └─ DevicesEndpointTests.cs
├─ Dockerfile.api
└─ Dockerfile.ingestion
```

---

### Task 1: Solution, projekty, reference, balíčky, konvence

Vytvoří prázdné (ale kompilovatelné) řešení se všemi projekty, referencemi mezi vrstvami, NuGet balíčky a profesionálními konvencemi (`Directory.Build.props`, `.editorconfig`).

**Files:**
- Create: `backend/IoT.sln`, `backend/Directory.Build.props`, `backend/.editorconfig`
- Create: všechny `*.csproj` (přes `dotnet new`)

- [ ] **Step 1: Vytvoř solution a strukturu projektů**

Vše spouštěj z `backend/` (adresář už existuje, obsahuje jen `README.md`).

```bash
cd backend
dotnet new sln -n IoT
dotnet new classlib -n IoT.Core         -o src/IoT.Core
dotnet new classlib -n IoT.Infrastructure -o src/IoT.Infrastructure
dotnet new worker  -n IoT.Ingestion     -o src/IoT.Ingestion
dotnet new webapi  -n IoT.Api           -o src/IoT.Api --use-controllers
dotnet new xunit   -n IoT.Core.Tests    -o tests/IoT.Core.Tests
dotnet new xunit   -n IoT.Api.Tests     -o tests/IoT.Api.Tests

# odstraň výchozí generované třídy, které nahradíme
rm -f src/IoT.Core/Class1.cs src/IoT.Infrastructure/Class1.cs
rm -f src/IoT.Api/WeatherForecast.cs src/IoT.Api/Controllers/WeatherForecastController.cs
rm -f tests/IoT.Core.Tests/UnitTest1.cs tests/IoT.Api.Tests/UnitTest1.cs

dotnet sln add src/IoT.Core src/IoT.Infrastructure src/IoT.Ingestion src/IoT.Api \
               tests/IoT.Core.Tests tests/IoT.Api.Tests
```

- [ ] **Step 2: Reference mezi projekty**

```bash
cd backend
dotnet add src/IoT.Infrastructure reference src/IoT.Core
dotnet add src/IoT.Ingestion      reference src/IoT.Infrastructure
dotnet add src/IoT.Api            reference src/IoT.Infrastructure
dotnet add tests/IoT.Core.Tests   reference src/IoT.Core
dotnet add tests/IoT.Api.Tests    reference src/IoT.Api
```

- [ ] **Step 3: NuGet balíčky**

```bash
cd backend
# Infrastructure: EF Core (Npgsql), Npgsql (COPY), MQTTnet, konfigurace/DI/logging abstrakce
dotnet add src/IoT.Infrastructure package Npgsql.EntityFrameworkCore.PostgreSQL
dotnet add src/IoT.Infrastructure package Npgsql
dotnet add src/IoT.Infrastructure package MQTTnet --version 4.3.7.1207
dotnet add src/IoT.Infrastructure package Microsoft.Extensions.Options.ConfigurationExtensions
dotnet add src/IoT.Infrastructure package Microsoft.Extensions.Hosting.Abstractions
# Api: OpenAPI (built-in) + health check nad DbContextem
dotnet add src/IoT.Api package Microsoft.AspNetCore.OpenApi
dotnet add src/IoT.Api package Microsoft.Extensions.Diagnostics.HealthChecks.EntityFrameworkCore
# Api.Tests: integrační testy + InMemory DB (bez závislosti na Postgresu)
dotnet add tests/IoT.Api.Tests package Microsoft.AspNetCore.Mvc.Testing
dotnet add tests/IoT.Api.Tests package Microsoft.EntityFrameworkCore.InMemory
```

- [ ] **Step 4: `Directory.Build.props` (společné vlastnosti pro všechny projekty)**

Create `backend/Directory.Build.props`:

```xml
<Project>
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <LangVersion>latest</LangVersion>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <InvariantGlobalization>true</InvariantGlobalization>
    <GenerateDocumentationFile>false</GenerateDocumentationFile>
  </PropertyGroup>
</Project>
```

Pozn.: `dotnet new` vygeneroval `<TargetFramework>` do každého `*.csproj`. Nech je být — `Directory.Build.props` je import; duplicitní hodnota nevadí, ale pokud by SDK hlásilo konflikt, odstraň `<TargetFramework>` a `<Nullable>`/`<ImplicitUsings>` z jednotlivých `*.csproj` (jsou už v props).

- [ ] **Step 5: `.editorconfig` (jednotný styl)**

Create `backend/.editorconfig`:

```ini
root = true

[*.cs]
indent_style = space
indent_size = 4
insert_final_newline = true
charset = utf-8
dotnet_sort_system_directives_first = true
csharp_new_line_before_open_brace = all
dotnet_style_namespace_match_folder = true
csharp_style_namespace_declarations = file_scoped:warning
```

- [ ] **Step 6: Ověř, že se prázdná kostra buildne**

Run: `cd backend && dotnet build`
Expected: `Build succeeded` (0 Error). Varování 0 (nový kód je prázdný).

- [ ] **Step 7: Commit**

```bash
cd backend && cd ..
git add backend/
git commit -m "Fáze 4: kostra řešení backendu (.NET) — projekty, reference, balíčky, konvence

Solution IoT (Core/Infrastructure/Ingestion/Api + 2× testy), reference mezi
vrstvami, NuGet balíčky, Directory.Build.props (net10, nullable, warnings-as-errors),
.editorconfig. Zatím prázdné třídy — plní další tasky.

Ověřeno: dotnet build (Build succeeded).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: IoT.Core — kanonický payload + parser (TDD)

Kanonický DTO telemetrie dle ROADMAP §6 a čistá funkce parsování JSON → DTO. Parsování je plumbing (deserializace kontraktu); **business validaci** (rozsahy, povinná pole nad rámec schématu) dopisuje autor.

**Files:**
- Create: `backend/src/IoT.Core/Telemetry/TelemetryPayload.cs`
- Create: `backend/src/IoT.Core/Telemetry/TelemetryPayloadParser.cs`
- Test: `backend/tests/IoT.Core.Tests/TelemetryPayloadParserTests.cs`

- [ ] **Step 1: Napiš padající test**

Create `backend/tests/IoT.Core.Tests/TelemetryPayloadParserTests.cs`:

```csharp
using IoT.Core.Telemetry;
using Xunit;

namespace IoT.Core.Tests;

public class TelemetryPayloadParserTests
{
    [Fact]
    public void Parse_ValidPayload_ReturnsCanonicalModel()
    {
        const string json = """
        {
          "schema": "v1",
          "device_id": "esp32-ab12cd",
          "ts": 1717490000,
          "seq": 10432,
          "measurements": [
            { "ch": "co2",  "v": 812,  "u": "ppm" },
            { "ch": "temp", "v": 23.4, "u": "Cel" }
          ]
        }
        """;

        var payload = TelemetryPayloadParser.Parse(json);

        Assert.Equal("esp32-ab12cd", payload.DeviceId);
        Assert.Equal(10432, payload.Seq);
        Assert.Equal(1717490000, payload.Ts);
        Assert.Equal(2, payload.Measurements.Count);
        Assert.Equal("co2", payload.Measurements[0].Channel);
        Assert.Equal(812, payload.Measurements[0].Value);
        Assert.Equal("Cel", payload.Measurements[1].Unit);
    }

    [Fact]
    public void Parse_Garbage_ThrowsFormatException()
    {
        Assert.Throws<FormatException>(() => TelemetryPayloadParser.Parse("{ not json"));
    }
}
```

- [ ] **Step 2: Spusť test — musí selhat**

Run: `cd backend && dotnet test tests/IoT.Core.Tests`
Expected: FAIL — `TelemetryPayload`/`TelemetryPayloadParser` neexistují (build error CS0246).

- [ ] **Step 3: Implementuj DTO**

Create `backend/src/IoT.Core/Telemetry/TelemetryPayload.cs`:

```csharp
using System.Text.Json.Serialization;

namespace IoT.Core.Telemetry;

/// <summary>Kanonický payload telemetrie (ROADMAP §6). Jedna zpráva = N měření.</summary>
public sealed record TelemetryPayload(
    [property: JsonPropertyName("schema")] string Schema,
    [property: JsonPropertyName("device_id")] string DeviceId,
    [property: JsonPropertyName("ts")] long Ts,
    [property: JsonPropertyName("seq")] long Seq,
    [property: JsonPropertyName("measurements")] IReadOnlyList<Measurement> Measurements);

/// <summary>Jedno měření jednoho kanálu.</summary>
public sealed record Measurement(
    [property: JsonPropertyName("ch")] string Channel,
    [property: JsonPropertyName("v")] double Value,
    [property: JsonPropertyName("u")] string Unit);
```

- [ ] **Step 4: Implementuj parser**

Create `backend/src/IoT.Core/Telemetry/TelemetryPayloadParser.cs`:

```csharp
using System.Text.Json;

namespace IoT.Core.Telemetry;

/// <summary>
/// Deserializace kanonického JSON payloadu na <see cref="TelemetryPayload"/>.
/// Čistá funkce (testovatelná bez brokeru/DB). Business validace (rozsahy, povinná
/// pole, dedup) je věc ingestion vrstvy — dopisuje autor.
/// </summary>
public static class TelemetryPayloadParser
{
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    public static TelemetryPayload Parse(string json)
    {
        try
        {
            var payload = JsonSerializer.Deserialize<TelemetryPayload>(json, Options);
            return payload ?? throw new FormatException("Payload deserializován jako null.");
        }
        catch (JsonException ex)
        {
            throw new FormatException("Neplatný JSON telemetrie.", ex);
        }
    }
}
```

- [ ] **Step 5: Spusť test — musí projít**

Run: `cd backend && dotnet test tests/IoT.Core.Tests`
Expected: PASS (2 testy).

- [ ] **Step 6: Commit**

```bash
git add backend/src/IoT.Core backend/tests/IoT.Core.Tests
git commit -m "Fáze 4: IoT.Core — kanonický payload telemetrie + parser (TDD)

TelemetryPayload/Measurement (ROADMAP §6) a čistá funkce parsování JSON→DTO.
Business validaci a dedup dopisuje autor v ingestion vrstvě.

Ověřeno: dotnet test IoT.Core.Tests (2 passed).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: IoT.Core — kontrakty zápisu; IoT.Infrastructure — EF Core metadata

Port pro zápis telemetrie (`ITelemetryWriter`, `TelemetryRow`) v Core a EF Core `AppDbContext` mapovaný **database-first** na existující tabulky (`tenant/site/location/device/channel`).

**Files:**
- Create: `backend/src/IoT.Core/Telemetry/TelemetryRow.cs`
- Create: `backend/src/IoT.Core/Abstractions/ITelemetryWriter.cs`
- Create: `backend/src/IoT.Infrastructure/Metadata/Entities.cs`
- Create: `backend/src/IoT.Infrastructure/Metadata/AppDbContext.cs`

- [ ] **Step 1: `TelemetryRow` (řádek pro zápis)**

Create `backend/src/IoT.Core/Telemetry/TelemetryRow.cs`:

```csharp
namespace IoT.Core.Telemetry;

/// <summary>Jeden řádek určený k zápisu do hypertable <c>telemetry</c>.</summary>
public readonly record struct TelemetryRow(
    DateTimeOffset Time,
    string DeviceId,
    long ChannelId,
    double Value,
    short Quality,
    long Seq);
```

- [ ] **Step 2: `ITelemetryWriter` (port)**

Create `backend/src/IoT.Core/Abstractions/ITelemetryWriter.cs`:

```csharp
using IoT.Core.Telemetry;

namespace IoT.Core.Abstractions;

/// <summary>Dávkový zápis telemetrie do time-series úložiště (implementace v Infrastructure).</summary>
public interface ITelemetryWriter
{
    Task WriteAsync(IReadOnlyList<TelemetryRow> rows, CancellationToken ct);
}
```

- [ ] **Step 3: EF entity mapované na existující schéma**

Create `backend/src/IoT.Infrastructure/Metadata/Entities.cs`:

```csharp
namespace IoT.Infrastructure.Metadata;

// Database-first: názvy/sloupce se mapují ve fluent API v AppDbContext.
// Mapujeme jen hierarchii metadat potřebnou pro API skeleton; ostatní tabulky
// (device_config, command_log, …) doplní autor podle potřeby.

public sealed class Tenant
{
    public long Id { get; set; }
    public string Name { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; }
    public List<Site> Sites { get; } = [];
}

public sealed class Site
{
    public long Id { get; set; }
    public long TenantId { get; set; }
    public string Name { get; set; } = "";
    public string? Address { get; set; }
    public double? Latitude { get; set; }
    public double? Longitude { get; set; }
    public List<Location> Locations { get; } = [];
}

public sealed class Location
{
    public long Id { get; set; }
    public long SiteId { get; set; }
    public string? FloorLabel { get; set; }
    public string? Room { get; set; }
    public string? Name { get; set; }
    public List<Device> Devices { get; } = [];
}

public sealed class Device
{
    public string DeviceId { get; set; } = "";
    public long? LocationId { get; set; }
    public string? HwType { get; set; }
    public string? FwVersion { get; set; }
    public string? Serial { get; set; }
    public string? Mac { get; set; }
    public string Status { get; set; } = "unknown";
    public DateTimeOffset? LastSeen { get; set; }
    public DateTimeOffset RegisteredAt { get; set; }
    public int ConfigVersion { get; set; }
    public List<Channel> Channels { get; } = [];
}

public sealed class Channel
{
    public long Id { get; set; }
    public string DeviceId { get; set; } = "";
    public string Quantity { get; set; } = "";
    public string Unit { get; set; } = "";
    public double? ValMin { get; set; }
    public double? ValMax { get; set; }
}
```

- [ ] **Step 4: `AppDbContext` s ručním mapováním**

Create `backend/src/IoT.Infrastructure/Metadata/AppDbContext.cs`:

```csharp
using Microsoft.EntityFrameworkCore;

namespace IoT.Infrastructure.Metadata;

/// <summary>
/// EF Core kontext nad RELAČNÍMI metadaty. Database-first: schéma je zdroj pravdy
/// (infra/timescale/init/01_metadata.sql), migrace se z kódu NEgenerují.
/// Telemetrie jde mimo EF (Npgsql COPY) — viz NpgsqlTelemetryWriter.
/// </summary>
public sealed class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<Tenant> Tenants => Set<Tenant>();
    public DbSet<Site> Sites => Set<Site>();
    public DbSet<Location> Locations => Set<Location>();
    public DbSet<Device> Devices => Set<Device>();
    public DbSet<Channel> Channels => Set<Channel>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Tenant>(e =>
        {
            e.ToTable("tenant");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.Name).HasColumnName("name");
            e.Property(x => x.CreatedAt).HasColumnName("created_at");
        });

        b.Entity<Site>(e =>
        {
            e.ToTable("site");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.TenantId).HasColumnName("tenant_id");
            e.Property(x => x.Name).HasColumnName("name");
            e.Property(x => x.Address).HasColumnName("address");
            e.Property(x => x.Latitude).HasColumnName("latitude");
            e.Property(x => x.Longitude).HasColumnName("longitude");
            e.HasMany(x => x.Locations).WithOne().HasForeignKey(x => x.SiteId);
            e.HasOne<Tenant>().WithMany(t => t.Sites).HasForeignKey(x => x.TenantId);
        });

        b.Entity<Location>(e =>
        {
            e.ToTable("location");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.SiteId).HasColumnName("site_id");
            e.Property(x => x.FloorLabel).HasColumnName("floor_label");
            e.Property(x => x.Room).HasColumnName("room");
            e.Property(x => x.Name).HasColumnName("name");
        });

        b.Entity<Device>(e =>
        {
            e.ToTable("device");
            e.HasKey(x => x.DeviceId);
            e.Property(x => x.DeviceId).HasColumnName("device_id");
            e.Property(x => x.LocationId).HasColumnName("location_id");
            e.Property(x => x.HwType).HasColumnName("hw_type");
            e.Property(x => x.FwVersion).HasColumnName("fw_version");
            e.Property(x => x.Serial).HasColumnName("serial");
            e.Property(x => x.Mac).HasColumnName("mac");
            e.Property(x => x.Status).HasColumnName("status");
            e.Property(x => x.LastSeen).HasColumnName("last_seen");
            e.Property(x => x.RegisteredAt).HasColumnName("registered_at");
            e.Property(x => x.ConfigVersion).HasColumnName("config_version");
            e.HasMany(x => x.Channels).WithOne().HasForeignKey(x => x.DeviceId);
            e.HasOne<Location>().WithMany(l => l.Devices).HasForeignKey(x => x.LocationId);
        });

        b.Entity<Channel>(e =>
        {
            e.ToTable("channel");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.DeviceId).HasColumnName("device_id");
            e.Property(x => x.Quantity).HasColumnName("quantity");
            e.Property(x => x.Unit).HasColumnName("unit");
            e.Property(x => x.ValMin).HasColumnName("val_min");
            e.Property(x => x.ValMax).HasColumnName("val_max");
        });
    }
}
```

- [ ] **Step 5: Ověř build**

Run: `cd backend && dotnet build`
Expected: `Build succeeded`, 0 varování.

- [ ] **Step 6: Commit**

```bash
git add backend/src/IoT.Core backend/src/IoT.Infrastructure
git commit -m "Fáze 4: IoT.Core kontrakty zápisu + IoT.Infrastructure EF Core metadata

TelemetryRow + ITelemetryWriter (port). AppDbContext database-first mapovaný na
existující tabulky tenant/site/location/device/channel (schéma = zdroj pravdy,
migrace se z kódu negenerují).

Ověřeno: dotnet build (Build succeeded).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: IoT.Infrastructure — Npgsql COPY writer, MQTT options, DI

Produkční plumbing zápisu telemetrie (binární COPY, převzato z prototypu `benchmarks/dotnet/`), konfigurace MQTT (Options pattern) a `AddInfrastructure(config)` registrující DbContext + writer + options.

**Files:**
- Create: `backend/src/IoT.Infrastructure/Mqtt/MqttOptions.cs`
- Create: `backend/src/IoT.Infrastructure/Telemetry/NpgsqlTelemetryWriter.cs`
- Create: `backend/src/IoT.Infrastructure/DependencyInjection.cs`

- [ ] **Step 1: `MqttOptions`**

Create `backend/src/IoT.Infrastructure/Mqtt/MqttOptions.cs`:

```csharp
namespace IoT.Infrastructure.Mqtt;

/// <summary>Konfigurace připojení k MQTT brokeru (sekce "Mqtt" v appsettings).</summary>
public sealed class MqttOptions
{
    public const string SectionName = "Mqtt";

    public string Host { get; set; } = "localhost";
    public int Port { get; set; } = 1883;
    /// <summary>Shared subscription pro škálování ingestionu, např. "$share/ingest/v1/dev/+/telemetry".</summary>
    public string Topic { get; set; } = "$share/ingest/v1/dev/+/telemetry";
    public int Qos { get; set; } = 1;
    public string ClientId { get; set; } = "iot-ingestion";
}
```

- [ ] **Step 2: `NpgsqlTelemetryWriter` (binární COPY)**

Create `backend/src/IoT.Infrastructure/Telemetry/NpgsqlTelemetryWriter.cs`:

**Holá kostra:** tělo je stub s `TODO`. Referenční implementace COPY (z prototypu
`benchmarks/dotnet/`) je v komentáři jako vodítko pro autora. Třída nemá ctor
závislosti (aby `NpgsqlDataSource` nebyl nečtený parametr → CS9113 s warnings-as-errors);
autor si `NpgsqlDataSource` vstříkne až při implementaci (je registrovaný v DI).

```csharp
using IoT.Core.Abstractions;
using IoT.Core.Telemetry;

namespace IoT.Infrastructure.Telemetry;

/// <summary>
/// Zápis telemetrie do hypertable <c>telemetry</c>. V plné verzi jde vysoký zápisový
/// tok binárním COPY mimo EF (bez change-trackingu). Sloupec <c>time</c> = čas měření,
/// <c>received_at</c> doplní default DB; pozor channel_id je bigint (int8).
///
/// TODO (autor): implementovat dávkový binární COPY. Vzor (prototyp benchmarks/dotnet/):
///   await using var conn = await dataSource.OpenConnectionAsync(ct);
///   await using var w = await conn.BeginBinaryImportAsync(
///       "COPY telemetry (time,device_id,channel_id,value,quality,seq) FROM STDIN (FORMAT BINARY)", ct);
///   foreach (var r in rows) { await w.StartRowAsync(ct); ...WriteAsync(r.X, NpgsqlDbType.Y, ct)... }
///   await w.CompleteAsync(ct);
/// </summary>
public sealed class NpgsqlTelemetryWriter : ITelemetryWriter
{
    public Task WriteAsync(IReadOnlyList<TelemetryRow> rows, CancellationToken ct) =>
        throw new NotImplementedException("TODO (autor): dávkový binární COPY do telemetry.");
}
```

- [ ] **Step 3: `AddInfrastructure` (DI extension)**

Create `backend/src/IoT.Infrastructure/DependencyInjection.cs`:

```csharp
using IoT.Core.Abstractions;
using IoT.Infrastructure.Metadata;
using IoT.Infrastructure.Mqtt;
using IoT.Infrastructure.Telemetry;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;

namespace IoT.Infrastructure;

/// <summary>Registrace infrastruktury: DbContext (metadata), Npgsql zdroj + writer, MQTT options.</summary>
public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(this IServiceCollection services, IConfiguration config)
    {
        var connString = config.GetConnectionString("Timescale")
            ?? throw new InvalidOperationException("Chybí ConnectionStrings:Timescale v konfiguraci.");

        // EF Core nad metadaty
        services.AddDbContext<AppDbContext>(o => o.UseNpgsql(connString));

        // Sdílený Npgsql datasource pro COPY (mimo EF)
        services.AddSingleton(_ => new NpgsqlDataSourceBuilder(connString).Build());
        services.AddSingleton<ITelemetryWriter, NpgsqlTelemetryWriter>();

        // MQTT konfigurace (Options pattern)
        services.Configure<MqttOptions>(config.GetSection(MqttOptions.SectionName));

        return services;
    }
}
```

- [ ] **Step 4: Ověř build**

Run: `cd backend && dotnet build`
Expected: `Build succeeded`, 0 varování.

- [ ] **Step 5: Commit**

```bash
git add backend/src/IoT.Infrastructure
git commit -m "Fáze 4: IoT.Infrastructure — Npgsql COPY writer, MQTT options, DI

NpgsqlTelemetryWriter (binární COPY do telemetry, převzato z prototypu),
MqttOptions (Options pattern, shared subscription), AddInfrastructure registrující
DbContext + NpgsqlDataSource + writer + options.

Ověřeno: dotnet build (Build succeeded).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: IoT.Api — Program.cs, health, OpenAPI, GET /v1/devices

ASP.NET Core web app: DI (`AddInfrastructure`), Controllers, built-in OpenAPI, health check nad DbContextem, jeden průchozí endpoint `GET /v1/devices`.

**Files:**
- Modify: `backend/src/IoT.Api/Program.cs` (přepiš vygenerovaný)
- Create: `backend/src/IoT.Api/Controllers/DevicesController.cs`
- Modify: `backend/src/IoT.Api/appsettings.json`

- [ ] **Step 1: `Program.cs`**

Replace `backend/src/IoT.Api/Program.cs` obsahem:

```csharp
using IoT.Infrastructure;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddInfrastructure(builder.Configuration);
builder.Services.AddControllers();
builder.Services.AddOpenApi();
builder.Services.AddHealthChecks()
    .AddDbContextCheck<IoT.Infrastructure.Metadata.AppDbContext>("timescale");

var app = builder.Build();

app.MapOpenApi();               // /openapi/v1.json
app.MapControllers();
app.MapHealthChecks("/health");

app.Run();

// Zpřístupnění třídy Program pro WebApplicationFactory v integračních testech.
public partial class Program;
```

- [ ] **Step 2: `DevicesController`**

Create `backend/src/IoT.Api/Controllers/DevicesController.cs`:

**Holá kostra:** tělo je stub vracející prázdný seznam s `TODO` (endpoint tak vrací
200 + `[]` a projde smoke testem). Reálný dotaz přes `AppDbContext` dopisuje autor.
Kontroler proto zatím `AppDbContext` **nevstřikuje** (aby nebyl nečtený → warning).
Připojení k DB ověřuje `/health` (AddDbContextCheck), ne tento endpoint.

```csharp
using Microsoft.AspNetCore.Mvc;

namespace IoT.Api.Controllers;

/// <summary>Seznam zařízení z metadat. Průchozí endpoint skeletonu (rozšiřuje autor).</summary>
[ApiController]
[Route("v1/[controller]")]
public sealed class DevicesController : ControllerBase
{
    /// <summary>
    /// Vrátí seznam registrovaných zařízení.
    /// TODO (autor): vstříknout AppDbContext a načíst zařízení, např.:
    ///   await db.Devices.OrderBy(d => d.DeviceId)
    ///       .Select(d => new DeviceDto(d.DeviceId, d.HwType, d.Status, d.LastSeen)).ToListAsync(ct);
    /// </summary>
    [HttpGet]
    public Task<IReadOnlyList<DeviceDto>> Get(CancellationToken ct) =>
        Task.FromResult<IReadOnlyList<DeviceDto>>([]);
}

/// <summary>Výstupní DTO zařízení (odděleno od EF entity).</summary>
public sealed record DeviceDto(string DeviceId, string? HwType, string Status, DateTimeOffset? LastSeen);
```

- [ ] **Step 3: `appsettings.json` (Api)**

Replace `backend/src/IoT.Api/appsettings.json`:

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.AspNetCore": "Warning"
    }
  },
  "AllowedHosts": "*",
  "ConnectionStrings": {
    "Timescale": "Host=localhost;Port=5432;Username=iot;Password=iot-dev;Database=iot"
  }
}
```

- [ ] **Step 4: Ověř build**

Run: `cd backend && dotnet build`
Expected: `Build succeeded`, 0 varování.

- [ ] **Step 5: Commit**

```bash
git add backend/src/IoT.Api
git commit -m "Fáze 4: IoT.Api — Program, health, OpenAPI, GET /v1/devices

ASP.NET Core web app: AddInfrastructure, Controllers, built-in OpenAPI, health
check nad DbContextem (/health). DevicesController = průchozí endpoint skeletonu.
public partial Program kvůli integračním testům.

Ověřeno: dotnet build (Build succeeded).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: IoT.Api.Tests — integrační smoke test (InMemory DB)

Ověří, že se web app nahodí a `GET /v1/devices` vrátí 200 + JSON pole. DbContext se přepíše na EF InMemory provider → test nezávisí na běžícím Postgresu.

**Files:**
- Create: `backend/tests/IoT.Api.Tests/DevicesEndpointTests.cs`

- [ ] **Step 1: Napiš test**

Create `backend/tests/IoT.Api.Tests/DevicesEndpointTests.cs`:

```csharp
using System.Net;
using System.Net.Http.Json;
using IoT.Infrastructure.Metadata;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace IoT.Api.Tests;

public class DevicesEndpointTests : IClassFixture<DevicesEndpointTests.Factory>
{
    private readonly Factory _factory;

    public DevicesEndpointTests(Factory factory) => _factory = factory;

    [Fact]
    public async Task GetDevices_ReturnsOkAndJsonArray()
    {
        var client = _factory.CreateClient();

        var response = await client.GetAsync("/v1/devices");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var devices = await response.Content.ReadFromJsonAsync<List<Dictionary<string, object>>>();
        Assert.NotNull(devices);   // prázdné pole (InMemory DB bez seedu) → 200 + []
    }

    /// <summary>Test host: přepíše AppDbContext na EF InMemory (bez Postgresu).</summary>
    public sealed class Factory : WebApplicationFactory<Program>
    {
        protected override void ConfigureWebHost(Microsoft.AspNetCore.Hosting.IWebHostBuilder builder)
        {
            builder.ConfigureServices(services =>
            {
                var descriptors = services
                    .Where(d => d.ServiceType == typeof(DbContextOptions<AppDbContext>)
                             || d.ServiceType == typeof(AppDbContext))
                    .ToList();
                foreach (var d in descriptors)
                {
                    services.Remove(d);
                }

                services.AddDbContext<AppDbContext>(o => o.UseInMemoryDatabase("tests"));
            });
        }
    }
}
```

- [ ] **Step 2: Spusť test — musí projít**

Run: `cd backend && dotnet test tests/IoT.Api.Tests`
Expected: PASS (1 test). Health check nad InMemory DB neblokuje endpoint; test cílí jen na `/v1/devices`.

Pozn.: Pokud build spadne na `Program` (not accessible), ověř, že `Program.cs` končí `public partial class Program;` (Task 5, Step 1).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/IoT.Api.Tests
git commit -m "Fáze 4: IoT.Api.Tests — integrační smoke test GET /v1/devices

WebApplicationFactory s přepsaným DbContextem na EF InMemory (bez závislosti na
Postgresu). Ověří 200 + JSON pole.

Ověřeno: dotnet test IoT.Api.Tests (1 passed).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: IoT.Ingestion — Worker (subscribe + wiring, doménová logika jako TODO)

Worker Service: `AddInfrastructure`, připojení k brokeru (MQTTnet 4.3), subscribe na shared subscription, počítání a logování zpráv. Parsování → validace → dedup → mapování kanálu → zápis přes `ITelemetryWriter` je **jasně vyznačený TODO pro autora**.

**Files:**
- Modify: `backend/src/IoT.Ingestion/Program.cs`
- Create: `backend/src/IoT.Ingestion/IngestionWorker.cs`
- Modify: `backend/src/IoT.Ingestion/appsettings.json`
- Delete: `backend/src/IoT.Ingestion/Worker.cs` (vygenerovaný výchozí worker)

- [ ] **Step 1: Odstraň výchozí worker**

```bash
rm -f backend/src/IoT.Ingestion/Worker.cs
```

- [ ] **Step 2: `Program.cs`**

Replace `backend/src/IoT.Ingestion/Program.cs`:

```csharp
using IoT.Infrastructure;
using IoT.Ingestion;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddInfrastructure(builder.Configuration);
builder.Services.AddHostedService<IngestionWorker>();

var host = builder.Build();
host.Run();
```

- [ ] **Step 3: `IngestionWorker`**

Create `backend/src/IoT.Ingestion/IngestionWorker.cs`:

```csharp
using IoT.Infrastructure.Mqtt;
using Microsoft.Extensions.Options;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace IoT.Ingestion;

/// <summary>
/// Ingestion konzument: připojí se k brokeru a subscribe na telemetrii přes shared
/// subscription (škálování víc replikami). Zpracování zprávy je vyznačené jako TODO —
/// zde autor dopisuje parse → validaci → dedup (device_id+seq) → mapování kanálu →
/// dávkový zápis přes ITelemetryWriter.
/// </summary>
public sealed class IngestionWorker(
    IOptions<MqttOptions> options,
    ILogger<IngestionWorker> logger) : BackgroundService
{
    private readonly MqttOptions _mqtt = options.Value;
    private long _received;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var factory = new MqttFactory();
        using var client = factory.CreateMqttClient();

        client.ApplicationMessageReceivedAsync += e =>
        {
            var count = Interlocked.Increment(ref _received);
            if (count % 1000 == 1)
            {
                logger.LogInformation("Přijato zpráv: {Count} (poslední topic {Topic})",
                    count, e.ApplicationMessage.Topic);
            }

            // TODO (autor): payload = TelemetryPayloadParser.Parse(...);
            //   → validace, dedup dle (device_id, seq), mapování (device_id, ch) → channel_id,
            //   → dávkování a zápis přes vstříknutý ITelemetryWriter.WriteAsync(...).
            return Task.CompletedTask;
        };

        var clientOptions = new MqttClientOptionsBuilder()
            .WithTcpServer(_mqtt.Host, _mqtt.Port)
            .WithClientId(_mqtt.ClientId)
            .Build();

        await client.ConnectAsync(clientOptions, stoppingToken);
        await client.SubscribeAsync(
            new MqttTopicFilterBuilder()
                .WithTopic(_mqtt.Topic)
                .WithQualityOfServiceLevel((MqttQualityOfServiceLevel)_mqtt.Qos)
                .Build(),
            stoppingToken);

        logger.LogInformation("Ingestion připojen: {Host}:{Port}, topic {Topic}, QoS {Qos}",
            _mqtt.Host, _mqtt.Port, _mqtt.Topic, _mqtt.Qos);

        // Drž službu naživu; MQTTnet doručuje zprávy na vlastních vláknech.
        try
        {
            await Task.Delay(Timeout.Infinite, stoppingToken);
        }
        catch (OperationCanceledException)
        {
            // korektní ukončení (Ctrl+C / stop)
        }

        await client.DisconnectAsync();
    }
}
```

- [ ] **Step 4: `appsettings.json` (Ingestion)**

Replace `backend/src/IoT.Ingestion/appsettings.json`:

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.Hosting.Lifetime": "Information"
    }
  },
  "ConnectionStrings": {
    "Timescale": "Host=localhost;Port=5432;Username=iot;Password=iot-dev;Database=iot"
  },
  "Mqtt": {
    "Host": "localhost",
    "Port": 1883,
    "Topic": "$share/ingest/v1/dev/+/telemetry",
    "Qos": 1,
    "ClientId": "iot-ingestion"
  }
}
```

- [ ] **Step 5: Ověř build**

Run: `cd backend && dotnet build`
Expected: `Build succeeded`, 0 varování.

- [ ] **Step 6: Commit**

```bash
git add backend/src/IoT.Ingestion
git commit -m "Fáze 4: IoT.Ingestion — Worker (subscribe + wiring, logika jako TODO)

Worker Service: AddInfrastructure, připojení k EMQX (MQTTnet 4.3), subscribe na
shared subscription, počítání/logování zpráv. Parse→validace→dedup→zápis je
vyznačený TODO pro autora.

Ověřeno: dotnet build (Build succeeded).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Dockerfily + zapojení do infra/docker-compose.yml

Multi-stage Dockerfily pro Api a Ingestion (net10) a dva volitelné service pod novým profilem `backend` v `infra/docker-compose.yml`.

**Files:**
- Create: `backend/Dockerfile.api`, `backend/Dockerfile.ingestion`
- Modify: `infra/docker-compose.yml` (přidat služby `api`, `ingestion` pod profil `backend`)

- [ ] **Step 1: `Dockerfile.api`**

Create `backend/Dockerfile.api`:

```dockerfile
# Build z kořene backend/ (context: backend/)
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props .
COPY src/IoT.Core/IoT.Core.csproj src/IoT.Core/
COPY src/IoT.Infrastructure/IoT.Infrastructure.csproj src/IoT.Infrastructure/
COPY src/IoT.Api/IoT.Api.csproj src/IoT.Api/
RUN dotnet restore src/IoT.Api/IoT.Api.csproj
COPY src/ src/
RUN dotnet publish src/IoT.Api/IoT.Api.csproj -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
EXPOSE 8080
ENTRYPOINT ["dotnet", "IoT.Api.dll"]
```

- [ ] **Step 2: `Dockerfile.ingestion`**

Create `backend/Dockerfile.ingestion`:

```dockerfile
# Build z kořene backend/ (context: backend/)
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props .
COPY src/IoT.Core/IoT.Core.csproj src/IoT.Core/
COPY src/IoT.Infrastructure/IoT.Infrastructure.csproj src/IoT.Infrastructure/
COPY src/IoT.Ingestion/IoT.Ingestion.csproj src/IoT.Ingestion/
RUN dotnet restore src/IoT.Ingestion/IoT.Ingestion.csproj
COPY src/ src/
RUN dotnet publish src/IoT.Ingestion/IoT.Ingestion.csproj -c Release -o /app

FROM mcr.microsoft.com/dotnet/runtime:10.0
WORKDIR /app
COPY --from=build /app .
ENTRYPOINT ["dotnet", "IoT.Ingestion.dll"]
```

- [ ] **Step 3: Přidej služby do compose**

V `infra/docker-compose.yml` přidej do sekce `services:` (pod profil `backend`; v kontejnerech se broker/DB adresují jmény služeb `emqx`/`timescaledb`, ne `localhost`). Ověř přesné názvy služeb DB/brokeru v souboru (`timescaledb`, `emqx`) a případně uprav host/port níže:

```yaml
  api:
    build:
      context: ../backend
      dockerfile: Dockerfile.api
    profiles: ["backend"]
    depends_on: [timescaledb]
    environment:
      ConnectionStrings__Timescale: "Host=timescaledb;Port=5432;Username=iot;Password=iot-dev;Database=iot"
    ports:
      - "8080:8080"

  ingestion:
    build:
      context: ../backend
      dockerfile: Dockerfile.ingestion
    profiles: ["backend"]
    depends_on: [timescaledb, emqx]
    environment:
      ConnectionStrings__Timescale: "Host=timescaledb;Port=5432;Username=iot;Password=iot-dev;Database=iot"
      Mqtt__Host: "emqx"
      Mqtt__Port: "1883"
```

- [ ] **Step 4: Ověř, že compose je validní**

Run: `cd infra && sg docker -c 'docker compose --profile backend config >/dev/null && echo OK'`
Expected: `OK` (žádná YAML/schema chyba). Build image se ověří v Tasku 9.

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile.api backend/Dockerfile.ingestion infra/docker-compose.yml
git commit -m "Fáze 4: Dockerfily (api, ingestion) + služby v compose (profil backend)

Multi-stage build (net10 SDK → aspnet/runtime), služby api+ingestion pod profilem
'backend', v kontejneru adresují timescaledb/emqx jmény služeb.

Ověřeno: docker compose --profile backend config (validní).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Finální ověření (build + testy + živé připojení) a dokumentace zdrojů

Ověří kompletní kostru proti běžící infrastruktuře a doplní odkazy na dokumentaci použitých technologií (standing instrukce autora — [docs/reference/externi-zdroje.md](../../reference/externi-zdroje.md)).

**Files:**
- Modify: `docs/reference/externi-zdroje.md`
- Modify: `backend/README.md`

- [ ] **Step 1: Build + všechny testy**

Run: `cd backend && dotnet build && dotnet test`
Expected: `Build succeeded`, 0 varování; testy: 3 passed (2× Core, 1× Api).

- [ ] **Step 2: Nahoď infrastrukturu**

Run: `cd infra && sg docker -c 'docker compose up -d' && sleep 5 && sg docker -c 'docker compose ps'`
Expected: `timescaledb` a `emqx` běží (healthy/up).

- [ ] **Step 3: Ověř API proti živé DB**

```bash
cd backend
dotnet run --project src/IoT.Api &          # nastartuje na http://localhost:5xxx nebo :8080
sleep 8
# zjisti port z logu (řádek "Now listening on: http://localhost:PORT"); dosaď níže:
curl -fsS http://localhost:PORT/health && echo
curl -fsS http://localhost:PORT/v1/devices && echo
kill %1
```
Expected: `/health` → `Healthy`; `/v1/devices` → `[]` (prázdná DB) nebo JSON pole zařízení, pokud běžel seed. HTTP 200 v obou.

Pozn.: Pokud health hlásí Unhealthy, DB neběží nebo sedí špatný connection string — zkontroluj `infra` kontejnery a `ConnectionStrings:Timescale`.

- [ ] **Step 4: Ověř, že se ingestion připojí a přijímá**

```bash
cd backend
dotnet run --project src/IoT.Ingestion &
sleep 5
# v druhém terminálu pošli pár zpráv simulátorem (viz simulator/README);
# topic musí sedět s Mqtt:Topic (v1/dev/{id}/telemetry).
sleep 5
kill %1
```
Expected: v logu ingestionu `Ingestion připojen: localhost:1883 ...` a po publikaci `Přijato zpráv: N ...`.

- [ ] **Step 5: Doplň dokumentaci použitých technologií**

Do `docs/reference/externi-zdroje.md` přidej novou sekci (autor je pak cituje v textu). Uprav tabulku:

```markdown
## Backend implementace (.NET, Fáze 4)

| Zdroj | URL | Podkládá |
|---|---|---|
| ASP.NET Core — Web API (Controllers) | https://learn.microsoft.com/aspnet/core/web-api/ | REST API vrstva, [ApiController], routing |
| .NET — Worker Services / BackgroundService | https://learn.microsoft.com/dotnet/core/extensions/workers | samostatná ingestion služba (hostovaný BackgroundService) |
| EF Core — mapování na existující DB (fluent API) | https://learn.microsoft.com/ef/core/modeling/ | database-first mapování metadat (ToTable/HasColumnName) |
| Npgsql — Binary COPY (bulk insert) | https://www.npgsql.org/doc/copy.html | dávkový zápis telemetrie mimo EF |
| Npgsql — NpgsqlDataSource | https://www.npgsql.org/doc/basic-usage.html | sdílený zdroj spojení pro COPY |
| MQTTnet — MQTT klient (dokumentace) | https://github.com/dotnet/MQTTnet/wiki | připojení, subscribe, shared subscriptions |
| ASP.NET Core — Health checks | https://learn.microsoft.com/aspnet/core/host-and-deploy/health-checks | /health nad DbContextem |
| ASP.NET Core — OpenAPI (built-in) | https://learn.microsoft.com/aspnet/core/fundamentals/openapi/ | generování OpenAPI dokumentu |
| .NET — Options pattern | https://learn.microsoft.com/dotnet/core/extensions/options | konfigurace MQTT přes silně typované Options |
| Integrační testy (WebApplicationFactory) | https://learn.microsoft.com/aspnet/core/test/integration-tests | smoke test API bez reálné DB |
```

- [ ] **Step 6: Aktualizuj `backend/README.md`**

Nahraď `backend/README.md`, ať popisuje reálnou strukturu skeletonu (projekty, jak spustit Api/Ingestion, co je hotové a co dopisuje autor). Odkaž na [docs/design/backend-struktura.md](../docs/design/backend-struktura.md).

- [ ] **Step 7: Commit**

```bash
git add docs/reference/externi-zdroje.md backend/README.md
git commit -m "Fáze 4: ověření skeletonu (build+testy+živé připojení) + zdroje dokumentace

Ověřeno: dotnet build+test (3 passed); API /health=Healthy, /v1/devices=200 proti
živé TimescaleDB; ingestion se připojil k EMQX a přijímá zprávy. Doplněny odkazy
na dokumentaci .NET/EF Core/Npgsql/MQTTnet do externi-zdroje.md.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review (kontrola plánu proti specifikaci)

- **Pokrytí specifikace** (design doc):
  - Vrstvené řešení Core/Infrastructure/Ingestion/Api + testy → Task 1. ✅
  - Ingestion jako samostatná služba (shared subs) → Task 7 + compose Task 8. ✅
  - EF Core database-first, ruční mapování → Task 3. ✅
  - Telemetrie mimo ORM (Npgsql COPY) → Task 4. ✅
  - Controllers + OpenAPI, verzované /v1, health checks → Task 5. ✅
  - Options pattern, structured logging → Task 4/5/7. ✅
  - xUnit testy → Task 2 (Core), Task 6 (Api). ✅
  - Directory.Build.props (nullable, warnings-as-errors), .editorconfig → Task 1. ✅
  - Dockerfily + zapojení do compose → Task 8. ✅
  - Jeden průchozí endpoint GET /v1/devices + /health, ověřené připojení → Task 5 + Task 9. ✅
  - Bez CI (rozhodnuto) → není task. ✅
  - Doplnění dokumentace zdrojů (standing instrukce) → Task 9. ✅
- **Placeholder scan:** TODO v `IngestionWorker` je záměrná hranice „skeleton vs. autor", ne placeholder plánu — každý task má konkrétní kód/příkazy. ✅
- **Konzistence typů:** `ITelemetryWriter.WriteAsync(IReadOnlyList<TelemetryRow>, CancellationToken)` (Task 3) = signatura použitá v `NpgsqlTelemetryWriter` (Task 4). `TelemetryRow` pole (Time/DeviceId/ChannelId/Value/Quality/Seq) = sloupce COPY (Task 4). `MqttOptions` (Host/Port/Topic/Qos/ClientId) = použití ve Worker (Task 7) a appsettings. `public partial class Program` (Task 5) = `WebApplicationFactory<Program>` (Task 6). ✅
- **Riziková místa (řeší se v exekuci):** přesné verze EF Core 10 / Npgsql balíčků (`dotnet add package` bere aktuální — build ověří); `TreatWarningsAsErrors` může zachytit analyzer varování (opraví se u konkrétního místa); přesné názvy služeb v compose (`timescaledb`/`emqx`) ověřit v Tasku 8.
