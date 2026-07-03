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
