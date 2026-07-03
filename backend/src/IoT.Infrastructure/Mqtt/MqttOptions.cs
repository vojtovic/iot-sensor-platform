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
