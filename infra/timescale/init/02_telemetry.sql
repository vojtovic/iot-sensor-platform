-- ════════════════════════════════════════════════════════════════════════
--  Telemetrie  (ROADMAP §5)  — TIME-SERIES, TimescaleDB hypertable
--
--  Princip: zápisově náročná data měření jdou do hypertable partitionované
--  podle času. Metadata zůstávají v relačních tabulkách (01_metadata.sql).
--
--  Retention / downsampling (continuous aggregates) přijde ve Fázi 4.
-- ════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE telemetry (
    time        timestamptz NOT NULL,               -- čas měření (z 'ts' zařízení)
    device_id   text NOT NULL REFERENCES device(device_id) ON DELETE CASCADE,
    channel_id  bigint NOT NULL REFERENCES channel(id) ON DELETE CASCADE,
    value       double precision NOT NULL,
    quality     smallint NOT NULL DEFAULT 0,        -- 0 = ok; >0 = příznak kvality
    seq         bigint,                             -- monotónní čítač ze zařízení (dedup/řazení)
    received_at timestamptz NOT NULL DEFAULT now()  -- čas příjmu na serveru (vs. čas vzniku)
);

-- Hypertable partitionovaná podle času (chunky po 7 dnech).
SELECT create_hypertable('telemetry', by_range('time', INTERVAL '7 days'));

-- Dotazy typicky: "poslední hodnoty kanálu v čase" → index (channel_id, time).
CREATE INDEX idx_telemetry_channel_time ON telemetry (channel_id, time DESC);
CREATE INDEX idx_telemetry_device_time  ON telemetry (device_id, time DESC);

-- Pozn.: deduplikace dle (device_id, seq) se NEdělá unikátním indexem.
-- TimescaleDB vyžaduje, aby unikátní index na hypertable obsahoval i partitioning
-- sloupec (time) — což by smysl dedupu rozbilo (stejné seq v jiném čase by prošlo).
-- Dedup proto řeší ingestion vrstva (Fáze 4, ROADMAP §4).

