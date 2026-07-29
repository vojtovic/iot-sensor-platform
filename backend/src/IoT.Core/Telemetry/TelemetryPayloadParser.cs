

using System.Text.Json;
namespace IoT.Core.Telemetry;

public static class TelemetryPayloadParser
{
    public static TelemetryPayload Parse(string json)
    {
        try
        {
            return System.Text.Json.JsonSerializer.Deserialize<TelemetryPayload>(json)
                ?? throw new FormatException("Deserialized payload is null");
        }
        catch (System.Text.Json.JsonException ex)
        {
            throw new FormatException("Invalid JSON format", ex);
        }
    }
}