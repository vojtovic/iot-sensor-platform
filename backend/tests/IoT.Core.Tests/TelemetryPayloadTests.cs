using System.Text.Json;
using IoT.Core.Telemetry;
using Xunit;

namespace IoT.Core.Tests;

public class TelemetryPayloadTests
{
    [Fact]
    public void Deserializes_wire_json_into_record()
    {
        // Arrange – přesně to, co posílá simulátor
        const string json = """
        {
          "schema": "v1",
          "device_id": "esp32-sim-001",
          "ts": 1717490000,
          "seq": 42,
          "measurements": [
            { "ch": "co2",  "v": 812,  "u": "ppm" },
            { "ch": "temp", "v": 23.4, "u": "Cel" }
          ]
        }
        """;

        // Act
        var payload = JsonSerializer.Deserialize<TelemetryPayload>(json);

        // Assert
        Assert.NotNull(payload);
        Assert.Equal("v1", payload.Schema);
        Assert.Equal("esp32-sim-001", payload.DeviceId);
        Assert.Equal(1717490000L, payload.Timestamp);
        Assert.Equal(42L, payload.SequenceNumber);
        Assert.Equal(2, payload.Measurements.Count);
        Assert.Equal("co2", payload.Measurements[0].Channel);
        Assert.Equal(812.0, payload.Measurements[0].Value);
        Assert.Equal("Cel", payload.Measurements[1].Unit);
    }
}