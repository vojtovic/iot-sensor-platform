namespace IoT.Infrastructure.Metadata;

// Database-first: názvy/sloupce se mapují ve fluent API v AppDbContext.
// Mapujeme jen hierarchii metadat potřebnou pro API skeleton; ostatní tabulky
// (device_config, command_log, …) doplní autor podle potřeby.

public sealed class Tenant
{
    public long Id { get; set; }
    public string Name { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; }
    public List<Site> Sites { get; } = [];
}

public sealed class Site
{
    public long Id { get; set; }
    public long TenantId { get; set; }
    public string Name { get; set; } = "";
    public string? Address { get; set; }
    public double? Latitude { get; set; }
    public double? Longitude { get; set; }
    public List<Location> Locations { get; } = [];
}

public sealed class Location
{
    public long Id { get; set; }
    public long SiteId { get; set; }
    public string? FloorLabel { get; set; }
    public string? Room { get; set; }
    public string? Name { get; set; }
    public List<Device> Devices { get; } = [];
}

public sealed class Device
{
    public string DeviceId { get; set; } = "";
    public long? LocationId { get; set; }
    public string? HwType { get; set; }
    public string? FwVersion { get; set; }
    public string? Serial { get; set; }
    public string? Mac { get; set; }
    public string Status { get; set; } = "unknown";
    public DateTimeOffset? LastSeen { get; set; }
    public DateTimeOffset RegisteredAt { get; set; }
    public int ConfigVersion { get; set; }
    public List<Channel> Channels { get; } = [];
}

public sealed class Channel
{
    public long Id { get; set; }
    public string DeviceId { get; set; } = "";
    public string Quantity { get; set; } = "";
    public string Unit { get; set; } = "";
    public double? ValMin { get; set; }
    public double? ValMax { get; set; }
}
