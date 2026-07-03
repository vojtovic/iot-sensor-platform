using IoT.Core.Telemetry;

namespace IoT.Core.Abstractions;

/// <summary>Dávkový zápis telemetrie do time-series úložiště (implementace v Infrastructure).</summary>
public interface ITelemetryWriter
{
    Task WriteAsync(IReadOnlyList<TelemetryRow> rows, CancellationToken ct);
}
