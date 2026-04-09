-- OTEL Metrics table for Claude Code telemetry
-- Run this in a Databricks SQL warehouse or via create_table.py
--
-- Replace <catalog> and <schema> with your UC catalog/schema names.
-- Example: USE CATALOG my_catalog; CREATE SCHEMA IF NOT EXISTS my_schema;

USE CATALOG ${UC_CATALOG};

CREATE SCHEMA IF NOT EXISTS ${UC_SCHEMA}
  COMMENT 'OTEL telemetry from Claude Code CLI';

CREATE TABLE IF NOT EXISTS ${UC_SCHEMA}.claude_otel_metrics (
  resource_attributes  MAP<STRING, STRING>,
  scope_name           STRING,
  scope_version        STRING,
  metric_name          STRING,
  metric_description   STRING,
  metric_unit          STRING,
  start_time_unix_nano BIGINT,
  time_unix_nano       BIGINT,
  value_as_double      DOUBLE,
  value_as_int         BIGINT,
  histogram_count      BIGINT,
  histogram_sum        DOUBLE,
  aggregation_temporality INT,
  is_monotonic         BOOLEAN,
  attributes           MAP<STRING, STRING>,
  exemplars            ARRAY<STRUCT<
    filtered_attributes MAP<STRING, STRING>,
    time_unix_nano      BIGINT,
    value_as_double     DOUBLE,
    span_id             STRING,
    trace_id            STRING
  >>,
  flags                INT
)
USING DELTA
COMMENT 'OTLP metrics from Claude Code CLI'
TBLPROPERTIES (
  'otel.schemaVersion' = 'v1',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.autoOptimize.optimizeWrite' = 'true'
);
