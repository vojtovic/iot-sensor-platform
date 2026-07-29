using System.Text.Json.Serialization;

namespace IoT.Core.Telemetry;

public sealed record TelemetryPayload
( 
    [property:JsonPropertyName("schema")]
    string Schema,

    [property:JsonPropertyName("device_id")]
    string DeviceId,

    [property:JsonPropertyName("ts")]
    long Timestamp,

    [property:JsonPropertyName("seq")]
    long SequenceNumber,

    [property:JsonPropertyName("measurements")]
    IReadOnlyList<Measurement> Measurements);

public sealed record Measurement
( 
    [property:JsonPropertyName("ch")]
    string Channel,

    [property:JsonPropertyName("v")]
    double Value,

    [property:JsonPropertyName("u")]
    string Unit);