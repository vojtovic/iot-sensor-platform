using IoT.Core.Abstractions;
using IoT.Infrastructure.Metadata;
using IoT.Infrastructure.Mqtt;
using IoT.Infrastructure.Telemetry;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;

namespace IoT.Infrastructure;

/// <summary>Registrace infrastruktury: DbContext (metadata), Npgsql zdroj + writer, MQTT options.</summary>
public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(this IServiceCollection services, IConfiguration config)
    {
        var connString = config.GetConnectionString("Timescale")
            ?? throw new InvalidOperationException("Chybí ConnectionStrings:Timescale v konfiguraci.");

        // EF Core nad metadaty
        services.AddDbContext<AppDbContext>(o => o.UseNpgsql(connString));

        // Sdílený Npgsql datasource pro COPY (mimo EF)
        services.AddSingleton(_ => new NpgsqlDataSourceBuilder(connString).Build());
        services.AddSingleton<ITelemetryWriter, NpgsqlTelemetryWriter>();

        // MQTT konfigurace (Options pattern)
        services.Configure<MqttOptions>(config.GetSection(MqttOptions.SectionName));

        return services;
    }
}
