-- =============================================================================
-- Smart Energy Grid – Full SQL Setup
-- Steps 3 → 6: Hypertables, Chunk Experiments, Compression, Cont. Aggregates
-- Run as: psql -U postgres -d energy_db -f setup_timescaledb.sql
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- PREREQUISITES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3-A  Convert energy_readings to a hypertable (1-day chunks)
-- ─────────────────────────────────────────────────────────────────────────────
-- Assumes energy_readings already exists (created by subscriber.py).
-- Remove primary-key / unique constraints on (id) before converting
-- because TimescaleDB requires the partition column in every unique index.

ALTER TABLE energy_readings DROP CONSTRAINT IF EXISTS energy_readings_pkey;

SELECT create_hypertable(
    'energy_readings',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

-- Recommended indexes
CREATE INDEX IF NOT EXISTS idx_er_meter_ts
    ON energy_readings (meter_id, timestamp DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3-B  Baseline queries (record execution times with \timing on)
-- ─────────────────────────────────────────────────────────────────────────────
\timing on

-- Query 1: Average power consumption per hour today
SELECT time_bucket('1 hour', timestamp) AS hour,
       AVG(power)                        AS avg_power
FROM   energy_readings
WHERE  timestamp >= DATE_TRUNC('day', NOW())
GROUP  BY hour
ORDER  BY hour;

-- Query 2: Find peak consumption periods in the past week
SELECT time_bucket('15 minutes', timestamp) AS period,
       AVG(power)                            AS avg_power
FROM   energy_readings
WHERE  timestamp >= NOW() - INTERVAL '7 days'
GROUP  BY period
ORDER  BY avg_power DESC
LIMIT  10;

-- Query 3: Monthly consumption per meter
SELECT meter_id,
       DATE_TRUNC('month', timestamp) AS month,
       SUM(energy)                    AS total_energy
FROM   energy_readings
GROUP  BY meter_id, month
ORDER  BY month, total_energy DESC;

-- Query 4: Full dataset scan
SELECT COUNT(*), AVG(power), MAX(power), MIN(power)
FROM   energy_readings;

\timing off

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 4  Chunk-interval experiments (3-hour and 1-week variants)
-- ─────────────────────────────────────────────────────────────────────────────

-- 3-hour chunks
CREATE TABLE IF NOT EXISTS energy_readings_3h
    (LIKE energy_readings INCLUDING ALL);

SELECT create_hypertable(
    'energy_readings_3h', 'timestamp',
    chunk_time_interval => INTERVAL '3 hours',
    if_not_exists       => TRUE
);

-- 1-week chunks
CREATE TABLE IF NOT EXISTS energy_readings_week
    (LIKE energy_readings INCLUDING ALL);

SELECT create_hypertable(
    'energy_readings_week', 'timestamp',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists       => TRUE
);

-- Copy data into each variant (run AFTER historical data is loaded)
INSERT INTO energy_readings_3h   SELECT * FROM energy_readings;
INSERT INTO energy_readings_week SELECT * FROM energy_readings;

-- ── Run same 4 queries on each variant (restart PG between runs for cold cache)

\timing on
-- ── energy_readings_3h ──
-- Q1
SELECT time_bucket('1 hour', timestamp) AS hour, AVG(power)
FROM   energy_readings_3h
WHERE  timestamp >= DATE_TRUNC('day', NOW())
GROUP  BY hour ORDER BY hour;
-- Q2
SELECT time_bucket('15 minutes', timestamp) AS period, AVG(power)
FROM   energy_readings_3h
WHERE  timestamp >= NOW() - INTERVAL '7 days'
GROUP  BY period ORDER BY 2 DESC LIMIT 10;
-- Q3
SELECT meter_id, DATE_TRUNC('month', timestamp) AS month, SUM(energy)
FROM   energy_readings_3h
GROUP  BY meter_id, month ORDER BY month, 3 DESC;
-- Q4
SELECT COUNT(*), AVG(power), MAX(power), MIN(power) FROM energy_readings_3h;

-- ── energy_readings_week ──
-- Q1
SELECT time_bucket('1 hour', timestamp) AS hour, AVG(power)
FROM   energy_readings_week
WHERE  timestamp >= DATE_TRUNC('day', NOW())
GROUP  BY hour ORDER BY hour;
-- Q2
SELECT time_bucket('15 minutes', timestamp) AS period, AVG(power)
FROM   energy_readings_week
WHERE  timestamp >= NOW() - INTERVAL '7 days'
GROUP  BY period ORDER BY 2 DESC LIMIT 10;
-- Q3
SELECT meter_id, DATE_TRUNC('month', timestamp) AS month, SUM(energy)
FROM   energy_readings_week
GROUP  BY meter_id, month ORDER BY month, 3 DESC;
-- Q4
SELECT COUNT(*), AVG(power), MAX(power), MIN(power) FROM energy_readings_week;

\timing off

-- Chunk distribution inspection
SELECT chunk_name,
       pg_size_pretty(chunk_size) AS chunk_size,
       range_start,
       range_end
FROM   chunk_information
WHERE  hypertable_name = 'energy_readings'
ORDER  BY range_start;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 5  Compression
-- ─────────────────────────────────────────────────────────────────────────────

-- 5-A  Measure disk BEFORE compression
SELECT hypertable_name,
       pg_size_pretty(hypertable_size(format('%I', hypertable_name)::regclass))
           AS size_before
FROM   timescaledb_information.hypertables
WHERE  hypertable_name IN ('energy_readings','energy_readings_3h','energy_readings_week');

-- 5-B  Apply compression
-- energy_readings (1-day)
ALTER TABLE energy_readings
    SET (timescaledb.compress,
         timescaledb.compress_orderby   = 'timestamp DESC',
         timescaledb.compress_segmentby = 'meter_id');

SELECT add_compression_policy('energy_readings', INTERVAL '24 hours');

-- energy_readings_3h
ALTER TABLE energy_readings_3h
    SET (timescaledb.compress,
         timescaledb.compress_orderby   = 'timestamp DESC',
         timescaledb.compress_segmentby = 'meter_id');

SELECT add_compression_policy('energy_readings_3h', INTERVAL '3 hours');

-- energy_readings_week
ALTER TABLE energy_readings_week
    SET (timescaledb.compress,
         timescaledb.compress_orderby   = 'timestamp DESC',
         timescaledb.compress_segmentby = 'meter_id');

SELECT add_compression_policy('energy_readings_week', INTERVAL '1 week');

-- Manually compress all existing chunks immediately
SELECT compress_chunk(c) FROM show_chunks('energy_readings')      c;
SELECT compress_chunk(c) FROM show_chunks('energy_readings_3h')   c;
SELECT compress_chunk(c) FROM show_chunks('energy_readings_week') c;

-- 5-C  Measure disk AFTER compression
SELECT hypertable_name,
       pg_size_pretty(hypertable_size(format('%I', hypertable_name)::regclass))
           AS size_after
FROM   timescaledb_information.hypertables
WHERE  hypertable_name IN ('energy_readings','energy_readings_3h','energy_readings_week');

-- 5-D  Re-run Q2 and Q3 to compare post-compression query times
\timing on
-- Q2 post-compression
SELECT time_bucket('15 minutes', timestamp) AS period, AVG(power)
FROM   energy_readings
WHERE  timestamp >= NOW() - INTERVAL '7 days'
GROUP  BY period ORDER BY 2 DESC LIMIT 10;

-- Q3 post-compression
SELECT meter_id, DATE_TRUNC('month', timestamp) AS month, SUM(energy)
FROM   energy_readings
GROUP  BY meter_id, month ORDER BY month, 3 DESC;
\timing off

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 6  Continuous Aggregations
-- ─────────────────────────────────────────────────────────────────────────────

-- 15-minute aggregation view
CREATE MATERIALIZED VIEW IF NOT EXISTS energy_readings_15min
WITH (timescaledb.continuous) AS
SELECT meter_id,
       time_bucket('15 minutes', timestamp) AS bucket,
       AVG(power)                           AS avg_power,
       MAX(power)                           AS max_power,
       MIN(power)                           AS min_power,
       SUM(energy)                          AS total_energy,
       AVG(voltage)                         AS avg_voltage,
       AVG(current)                         AS avg_current
FROM   energy_readings
GROUP  BY meter_id, bucket
WITH NO DATA;

-- Hourly view (built on raw table for independence)
CREATE MATERIALIZED VIEW IF NOT EXISTS energy_readings_1h
WITH (timescaledb.continuous) AS
SELECT meter_id,
       time_bucket('1 hour', timestamp) AS bucket,
       AVG(power)                       AS avg_power,
       MAX(power)                       AS max_power,
       MIN(power)                       AS min_power,
       SUM(energy)                      AS total_energy
FROM   energy_readings
GROUP  BY meter_id, bucket
WITH NO DATA;

-- Daily view
CREATE MATERIALIZED VIEW IF NOT EXISTS energy_readings_1d
WITH (timescaledb.continuous) AS
SELECT meter_id,
       time_bucket('1 day', timestamp) AS bucket,
       AVG(power)                      AS avg_power,
       MAX(power)                      AS max_power,
       MIN(power)                      AS min_power,
       SUM(energy)                     AS total_energy
FROM   energy_readings
GROUP  BY meter_id, bucket
WITH NO DATA;

-- Backfill all views
CALL refresh_continuous_aggregate('energy_readings_15min', NULL, NULL);
CALL refresh_continuous_aggregate('energy_readings_1h',    NULL, NULL);
CALL refresh_continuous_aggregate('energy_readings_1d',    NULL, NULL);

-- Refresh policies
SELECT add_continuous_aggregate_policy(
    'energy_readings_15min',
    start_offset      => INTERVAL '3 days',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes'
);

SELECT add_continuous_aggregate_policy(
    'energy_readings_1h',
    start_offset      => INTERVAL '7 days',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

SELECT add_continuous_aggregate_policy(
    'energy_readings_1d',
    start_offset      => INTERVAL '30 days',
    end_offset        => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day'
);

-- ── Performance comparison: raw vs continuous aggregate ──
\timing on

-- Raw data query (last 24 h, single meter)
SELECT meter_id,
       time_bucket('15 minutes', timestamp) AS bucket,
       AVG(power) AS avg_power
FROM   energy_readings
WHERE  timestamp >= NOW() - INTERVAL '1 day'
  AND  meter_id  = '1000000001'
GROUP  BY meter_id, bucket
ORDER  BY bucket;

-- Continuous aggregate query (same window)
SELECT meter_id, bucket, avg_power
FROM   energy_readings_15min
WHERE  bucket    >= NOW() - INTERVAL '1 day'
  AND  meter_id   = '1000000001'
ORDER  BY bucket;

\timing off
