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
