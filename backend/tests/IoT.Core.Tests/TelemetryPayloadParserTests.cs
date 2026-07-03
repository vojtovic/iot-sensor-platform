using IoT.Core.Telemetry;
using Xunit;

namespace IoT.Core.Tests;

public class TelemetryPayloadParserTests
{
    [Fact]
    public void Parse_ValidPayload_ReturnsCanonicalModel()
    {
        const string json = """
        {
          "schema": "v1",
          "device_id": "esp32-ab12cd",
          "ts": 1717490000,
          "seq": 10432,
          "measurements": [
            { "ch": "co2",  "v": 812,  "u": "ppm" },
            { "ch": "temp", "v": 23.4, "u": "Cel" }
          ]
        }
        """;

        var payload = TelemetryPayloadParser.Parse(json);

        Assert.Equal("esp32-ab12cd", payload.DeviceId);
        Assert.Equal(10432, payload.Seq);
        Assert.Equal(1717490000, payload.Ts);
        Assert.Equal(2, payload.Measurements.Count);
        Assert.Equal("co2", payload.Measurements[0].Channel);
        Assert.Equal(812, payload.Measurements[0].Value);
        Assert.Equal("Cel", payload.Measurements[1].Unit);
    }

    [Fact]
    public void Parse_Garbage_ThrowsFormatException()
    {
        Assert.Throws<FormatException>(() => TelemetryPayloadParser.Parse("{ not json"));
    }
}
