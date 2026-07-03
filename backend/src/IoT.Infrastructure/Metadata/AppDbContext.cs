using Microsoft.EntityFrameworkCore;

namespace IoT.Infrastructure.Metadata;

/// <summary>
/// EF Core kontext nad RELAČNÍMI metadaty. Database-first: schéma je zdroj pravdy
/// (infra/timescale/init/01_metadata.sql), migrace se z kódu NEgenerují.
/// Telemetrie jde mimo EF (Npgsql COPY) — viz NpgsqlTelemetryWriter.
/// </summary>
public sealed class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<Tenant> Tenants => Set<Tenant>();
    public DbSet<Site> Sites => Set<Site>();
    public DbSet<Location> Locations => Set<Location>();
    public DbSet<Device> Devices => Set<Device>();
    public DbSet<Channel> Channels => Set<Channel>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Tenant>(e =>
        {
            e.ToTable("tenant");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.Name).HasColumnName("name");
            e.Property(x => x.CreatedAt).HasColumnName("created_at");
        });

        b.Entity<Site>(e =>
        {
            e.ToTable("site");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.TenantId).HasColumnName("tenant_id");
            e.Property(x => x.Name).HasColumnName("name");
            e.Property(x => x.Address).HasColumnName("address");
            e.Property(x => x.Latitude).HasColumnName("latitude");
            e.Property(x => x.Longitude).HasColumnName("longitude");
            e.HasMany(x => x.Locations).WithOne().HasForeignKey(x => x.SiteId);
            e.HasOne<Tenant>().WithMany(t => t.Sites).HasForeignKey(x => x.TenantId);
        });

        b.Entity<Location>(e =>
        {
            e.ToTable("location");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.SiteId).HasColumnName("site_id");
            e.Property(x => x.FloorLabel).HasColumnName("floor_label");
            e.Property(x => x.Room).HasColumnName("room");
            e.Property(x => x.Name).HasColumnName("name");
        });

        b.Entity<Device>(e =>
        {
            e.ToTable("device");
            e.HasKey(x => x.DeviceId);
            e.Property(x => x.DeviceId).HasColumnName("device_id");
            e.Property(x => x.LocationId).HasColumnName("location_id");
            e.Property(x => x.HwType).HasColumnName("hw_type");
            e.Property(x => x.FwVersion).HasColumnName("fw_version");
            e.Property(x => x.Serial).HasColumnName("serial");
            e.Property(x => x.Mac).HasColumnName("mac");
            e.Property(x => x.Status).HasColumnName("status");
            e.Property(x => x.LastSeen).HasColumnName("last_seen");
            e.Property(x => x.RegisteredAt).HasColumnName("registered_at");
            e.Property(x => x.ConfigVersion).HasColumnName("config_version");
            e.HasMany(x => x.Channels).WithOne().HasForeignKey(x => x.DeviceId);
            e.HasOne<Location>().WithMany(l => l.Devices).HasForeignKey(x => x.LocationId);
        });

        b.Entity<Channel>(e =>
        {
            e.ToTable("channel");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedOnAdd();
            e.Property(x => x.DeviceId).HasColumnName("device_id");
            e.Property(x => x.Quantity).HasColumnName("quantity");
            e.Property(x => x.Unit).HasColumnName("unit");
            e.Property(x => x.ValMin).HasColumnName("val_min");
            e.Property(x => x.ValMax).HasColumnName("val_max");
        });
    }
}
