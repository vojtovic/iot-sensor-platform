// Tenká ingestion služba (C#/.NET) — kandidát pro benchmark stacků (Fáze 3).
// Kontrakt stejný jako Python/Node: MQTT subscribe → parse → dávkový binární COPY
// do TimescaleDB. time = čas publikace (t_ns); latence se měří z DB.
//
// Zápis se serializuje přes System.Threading.Channels (MQTT handler → fronta →
// jeden konzument dělá COPY) — Npgsql spojení nesmí dělat víc COPY naráz.

using System.Text.Json;
using System.Threading.Channels;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;
using Npgsql;
using NpgsqlTypes;

string Env(string k, string d) => Environment.GetEnvironmentVariable(k) ?? d;

var mqttHost = Env("MQTT_HOST", "localhost");
var mqttPort = int.Parse(Env("MQTT_PORT", "1883"));
var topic = Env("MQTT_TOPIC", "bench/#");
var qos = int.Parse(Env("QOS", "1"));
var dsn = Env("DSN", "postgresql://iot:iot-dev@localhost:5432/iot");
var batchSize = int.Parse(Env("BATCH_SIZE", "500"));
var flushMs = double.Parse(Env("FLUSH_MS", "100"));

// DSN (URI) → Npgsql connection string
var uri = new Uri(dsn);
var ui = uri.UserInfo.Split(':');
var csb = new NpgsqlConnectionStringBuilder
{
    Host = uri.Host,
    Port = uri.Port,
    Username = ui[0],
    Password = ui.Length > 1 ? ui[1] : "",
    Database = uri.AbsolutePath.TrimStart('/'),
};

await using var conn = new NpgsqlConnection(csb.ConnectionString);
await conn.OpenAsync();

// channel_map: (device_id, quantity) → channel_id
// channel_id je bigint (int8) → čteme i píšeme jako long
var chan = new Dictionary<(string, string), long>();
await using (var cmd = new NpgsqlCommand("SELECT id, device_id, quantity FROM channel", conn))
await using (var rdr = await cmd.ExecuteReaderAsync())
    while (await rdr.ReadAsync())
        chan[(rdr.GetString(1), rdr.GetString(2))] = rdr.GetInt64(0);

var queue = Channel.CreateUnbounded<(DateTime ts, string dev, long cid, double val, long seq)>();

// Konzument: dávkuje z fronty a dělá binární COPY (size nebo flushMs).
var consumer = Task.Run(async () =>
{
    var batch = new List<(DateTime, string, long, double, long)>(batchSize);

    async Task Flush()
    {
        if (batch.Count == 0) return;
        await using var w = await conn.BeginBinaryImportAsync(
            "COPY telemetry (time,device_id,channel_id,value,quality,seq) FROM STDIN (FORMAT BINARY)");
        foreach (var (ts, dev, cid, val, seq) in batch)
        {
            await w.StartRowAsync();
            await w.WriteAsync(ts, NpgsqlDbType.TimestampTz);
            await w.WriteAsync(dev, NpgsqlDbType.Text);
            await w.WriteAsync(cid, NpgsqlDbType.Bigint);
            await w.WriteAsync(val, NpgsqlDbType.Double);
            await w.WriteAsync((short)0, NpgsqlDbType.Smallint);
            await w.WriteAsync(seq, NpgsqlDbType.Bigint);
        }
        await w.CompleteAsync();
        batch.Clear();
    }

    var reader = queue.Reader;
    while (true)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(flushMs));
            var row = await reader.ReadAsync(cts.Token);
            batch.Add(row);
            if (batch.Count >= batchSize) await Flush();
        }
        catch (OperationCanceledException)
        {
            await Flush();   // časové vyprázdnění
        }
    }
});

var factory = new MqttFactory();
var client = factory.CreateMqttClient();
client.ApplicationMessageReceivedAsync += e =>
{
    try
    {
        using var doc = JsonDocument.Parse(e.ApplicationMessage.ConvertPayloadToString());
        var root = doc.RootElement;
        var dev = root.GetProperty("device_id").GetString();
        var seq = root.GetProperty("seq").GetInt64();
        var tns = root.GetProperty("t_ns").GetInt64();
        var ts = DateTime.UnixEpoch.AddMilliseconds(tns / 1_000_000.0);
        foreach (var x in root.GetProperty("measurements").EnumerateArray())
        {
            var ch = x.GetProperty("ch").GetString();
            if (chan.TryGetValue((dev, ch), out var cid))
                queue.Writer.TryWrite((ts, dev, cid, x.GetProperty("v").GetDouble(), seq));
        }
    }
    catch { /* poškozená zpráva — přeskoč */ }
    return Task.CompletedTask;
};

var options = new MqttClientOptionsBuilder()
    .WithTcpServer(mqttHost, mqttPort)
    .WithClientId("dotnet-ingest")
    .Build();
await client.ConnectAsync(options);
await client.SubscribeAsync(new MqttTopicFilterBuilder()
    .WithTopic(topic)
    .WithQualityOfServiceLevel((MqttQualityOfServiceLevel)qos)
    .Build());

Console.WriteLine($"[dotnet] ingest: {mqttHost}:{mqttPort} topic={topic} qos={qos} " +
                  $"batch={batchSize}/{flushMs}ms channels={chan.Count}");

await consumer;   // běží navždy
