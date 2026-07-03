namespace IoT.Core.Telemetry;

/// <summary>Jeden řádek určený k zápisu do hypertable <c>telemetry</c>.</summary>
public readonly record struct TelemetryRow(
    DateTimeOffset Time,
    string DeviceId,
    long ChannelId,
    double Value,
    short Quality,
    long Seq);
