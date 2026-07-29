using IoT.Core.Telemetry;
using Xunit;

namespace IoT.Core.Tests;

public class TelemetryPayloadParserTests
{
    [Fact]
    public void Parse_broken_json_throws_FormatException()
    {
        const string json = "{ not json";   // rozbitý JSON

        Assert.Throws<FormatException>(() => TelemetryPayloadParser.Parse(json));
    }

    [Fact]
    public void Parse_valid_json_returns_payload()
    {
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

        TelemetryPayload payload = TelemetryPayloadParser.Parse(json);

        Assert.Equal("esp32-sim-001", payload.DeviceId);
        Assert.Equal(2, payload.Measurements.Count);
    }
}