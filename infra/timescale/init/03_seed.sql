-- ════════════════════════════════════════════════════════════════════════
--  Seed data pro lokální vývoj.
--
--  Minimální hierarchie + 2 zařízení (co2/temp/rh kanály), aby odpovídala
--  výchozímu běhu simulátoru (`python -m simulator --devices 2`).
--  Záměrně idempotentní (ON CONFLICT), aby nevadilo opakované spuštění.
-- ════════════════════════════════════════════════════════════════════════

INSERT INTO tenant (name) VALUES ('Demo Tenant')
    ON CONFLICT (name) DO NOTHING;

INSERT INTO site (tenant_id, name, address)
SELECT id, 'Hlavní budova', 'Univerzitní 1, Plzeň'
FROM tenant WHERE name = 'Demo Tenant'
    ON CONFLICT (tenant_id, name) DO NOTHING;

INSERT INTO floor (site_id, level_index, elevation_m)
SELECT s.id, 2, 6.0
FROM site s JOIN tenant t ON t.id = s.tenant_id
WHERE t.name = 'Demo Tenant' AND s.name = 'Hlavní budova'
    ON CONFLICT (site_id, level_index) DO NOTHING;

INSERT INTO location (site_id, floor_label, room, name)
SELECT s.id, '2.NP', '204', 'Laboratoř 204'
FROM site s JOIN tenant t ON t.id = s.tenant_id
WHERE t.name = 'Demo Tenant' AND s.name = 'Hlavní budova'
    ON CONFLICT (site_id, floor_label, room) DO NOTHING;

-- Dvě demo zařízení namapovaná do místnosti 204.
INSERT INTO device (device_id, location_id, hw_type, fw_version, status)
SELECT v.device_id, l.id, 'esp32', '1.0.0', 'unknown'
FROM (VALUES ('esp32-sim-001'), ('esp32-sim-002')) AS v(device_id)
CROSS JOIN location l
JOIN site s ON s.id = l.site_id
JOIN tenant t ON t.id = s.tenant_id
WHERE t.name = 'Demo Tenant' AND s.name = 'Hlavní budova' AND l.room = '204'
    ON CONFLICT (device_id) DO NOTHING;

-- Kanály co2 / temp / rh pro každé zařízení (kanonické jednotky dle SenML).
INSERT INTO channel (device_id, quantity, unit, val_min, val_max)
SELECT d.device_id, c.quantity, c.unit, c.val_min, c.val_max
FROM device d
CROSS JOIN (VALUES
    ('co2',  'ppm', 400.0, 5000.0),
    ('temp', 'Cel',  -10.0,   50.0),
    ('rh',   '%RH',    0.0,  100.0)
) AS c(quantity, unit, val_min, val_max)
WHERE d.device_id IN ('esp32-sim-001', 'esp32-sim-002')
    ON CONFLICT (device_id, quantity) DO NOTHING;

-- Poloha zařízení ve 2.NP pro digital twin (libovolné body v půdorysu).
INSERT INTO device_position (device_id, floor_id, x, y, z)
SELECT d.device_id, f.id, p.x, p.y, 1.2
FROM (VALUES ('esp32-sim-001', 3.0, 2.0), ('esp32-sim-002', 6.5, 4.0)) AS p(device_id, x, y)
JOIN device d ON d.device_id = p.device_id
JOIN location l ON l.id = d.location_id
JOIN floor f ON f.site_id = l.site_id AND f.level_index = 2
    ON CONFLICT (device_id) DO NOTHING;
