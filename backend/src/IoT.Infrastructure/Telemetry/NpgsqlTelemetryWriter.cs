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
