namespace IoT.Core.Telemetry;

/// <summary>
/// Deserializace kanonického JSON payloadu na <see cref="TelemetryPayload"/>.
/// Čistá funkce (testovatelná bez brokeru/DB).
///
/// TODO (autor): implementovat parsování a business validaci (rozsahy, povinná pole,
/// dedup device_id+seq). Kostra ponechává jen seam (podpis) — tělo dopisuje autor.
/// </summary>
public static class TelemetryPayloadParser
{
    public static TelemetryPayload Parse(string json) =>
        throw new NotImplementedException("TODO (autor): parsování a validace payloadu telemetrie.");
}
