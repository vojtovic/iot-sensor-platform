-- ════════════════════════════════════════════════════════════════════════
--  Metadatový model  (ROADMAP §5)
--  Relační metadata: hierarchie tenant → site → location → device → channel
--  + konfigurace, schopnosti, ukládací politika, příkazy, vizualizace.
--
--  Telemetrie (zápisově náročná) je samostatně v 02_telemetry.sql jako hypertable.
--  Spouští se automaticky při PRVNÍM startu kontejneru (docker-entrypoint-initdb.d).
-- ════════════════════════════════════════════════════════════════════════

-- ── Hierarchie nasazení ─────────────────────────────────────────────────

CREATE TABLE tenant (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE site (                                 -- budova
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   bigint NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name        text NOT NULL,
    address     text,
    latitude    double precision,
    longitude   double precision,
    UNIQUE (tenant_id, name)
);

CREATE TABLE location (                             -- zóna / místnost
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    floor_label text,                               -- patro (lidsky čitelné, např. "2.NP")
    room        text,                               -- místnost (např. "204")
    name        text,
    UNIQUE (site_id, floor_label, room)
);

-- ── Vizualizace budovy (digital twin, ROADMAP §5 + docs/design) ──────────

CREATE TABLE floor (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id         bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    level_index     int NOT NULL,                   -- pořadí patra (0 = přízemí)
    elevation_m     double precision,               -- výška podlahy nad referencí
    floorplan_asset text,                           -- 2,5D půdorys (obrázek/SVG)
    model3d_asset   text,                           -- volitelný 3D model (glTF) pro LOD detail
    UNIQUE (site_id, level_index)
);

-- ── Zařízení a kanály (MODULARITA = N kanálů na zařízení) ────────────────

CREATE TABLE device (
    device_id       text PRIMARY KEY,               -- business id z MQTT (např. "esp32-ab12cd")
    location_id     bigint REFERENCES location(id) ON DELETE SET NULL,
    hw_type         text,
    fw_version      text,
    serial          text,
    mac             text,
    status          text NOT NULL DEFAULT 'unknown' -- online | offline | unknown (přes LWT)
                    CHECK (status IN ('online', 'offline', 'unknown')),
    last_seen       timestamptz,
    registered_at   timestamptz NOT NULL DEFAULT now(),
    config_version  int NOT NULL DEFAULT 0
);

CREATE TABLE channel (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id   text NOT NULL REFERENCES device(device_id) ON DELETE CASCADE,
    quantity    text NOT NULL                       -- co2 | temp | rh | voc | pres | ...
                CHECK (quantity IN ('co2', 'temp', 'rh', 'voc', 'pres')),
    unit        text NOT NULL,                      -- kanonická jednotka (SenML/RFC 8428)
    val_min     double precision,
    val_max     double precision,
    calibration jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (device_id, quantity)
);

CREATE INDEX idx_channel_device ON channel (device_id);

-- ── Konfigurace, schopnosti, ukládací politika (ROADMAP §7 + §7b) ────────

CREATE TABLE device_config (                        -- žádaný stav (retained config)
    device_id   text NOT NULL REFERENCES device(device_id) ON DELETE CASCADE,
    version     int NOT NULL,
    json_config jsonb NOT NULL,                     -- sample_interval_s, report_policy, calibration…
    applied_at  timestamptz,                        -- kdy zařízení potvrdilo config_version
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (device_id, version)
);

CREATE TABLE device_capabilities (                  -- co zařízení umí (edge_policy, příkazy…)
    device_id    text PRIMARY KEY REFERENCES device(device_id) ON DELETE CASCADE,
    capabilities jsonb NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE measurement_policy (                   -- "report by exception" + heartbeat
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id   text REFERENCES device(device_id) ON DELETE CASCADE,
    channel_id  bigint REFERENCES channel(id) ON DELETE CASCADE,
    policy      jsonb NOT NULL,                      -- deadband, hystereze, heartbeat, min_interval
    version     int NOT NULL DEFAULT 1,
    enforced_at text NOT NULL DEFAULT 'backend'     -- kde se vynucuje (capability-aware hybrid)
                CHECK (enforced_at IN ('edge', 'backend')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    -- politika je buď na úrovni zařízení, nebo konkrétního kanálu (právě jedno)
    CHECK ((device_id IS NOT NULL) <> (channel_id IS NOT NULL))
);

-- ── Příkazy (downlink, command/ack vzor — ROADMAP §7b) ───────────────────

CREATE TABLE command_log (
    cmd_id      text PRIMARY KEY,                   -- korelační id (cmd → ack)
    device_id   text NOT NULL REFERENCES device(device_id) ON DELETE CASCADE,
    cmd         text NOT NULL,                      -- start | stop | set_interval | set_policy | …
    args        jsonb NOT NULL DEFAULT '{}'::jsonb,
    issued_by   text,                               -- kdo příkaz zadal (user/api key)
    status      text NOT NULL DEFAULT 'pending'     -- pending | acked | expired | failed
                CHECK (status IN ('pending', 'acked', 'expired', 'failed')),
    issued_at   timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz,                        -- expirace příkazu (neretained)
    acked_at    timestamptz
);

CREATE INDEX idx_command_log_device ON command_log (device_id, issued_at DESC);

-- ── Poloha senzoru pro digital twin (ROADMAP §5) ─────────────────────────

CREATE TABLE device_position (
    device_id   text PRIMARY KEY REFERENCES device(device_id) ON DELETE CASCADE,
    floor_id    bigint NOT NULL REFERENCES floor(id) ON DELETE CASCADE,
    x           double precision NOT NULL,
    y           double precision NOT NULL,
    z           double precision                    -- volitelné (výška ve 3D)
);

-- ── Bezpečnost a audit (lehké stuby, plně až Fáze 4) ─────────────────────

CREATE TABLE api_key (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL,
    key_hash    text NOT NULL UNIQUE,               -- nikdy neukládáme plaintext
    tenant_id   bigint REFERENCES tenant(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz
);

CREATE TABLE audit_event (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    actor       text,
    action      text NOT NULL,
    target      text,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb
);
