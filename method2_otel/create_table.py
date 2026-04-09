"""Method 2: Create Unity Catalog OTEL metrics table via Statement Execution API.

Usage:
    uv run python method2_otel/create_table.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState


def find_warehouse(client: WorkspaceClient) -> str:
    """Find a running SQL warehouse."""
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if warehouse_id:
        return warehouse_id

    warehouses = list(client.warehouses.list())
    running = [w for w in warehouses if w.state and "RUNNING" in str(w.state)]
    if not running:
        print("ERROR: No running SQL warehouse found. Set DATABRICKS_WAREHOUSE_ID in .env")
        sys.exit(1)
    print(f"Using warehouse: {running[0].name} ({running[0].id})")
    return running[0].id


def execute(client: WorkspaceClient, warehouse_id: str, sql: str):
    """Execute a SQL statement and print result."""
    print(f"  Executing: {sql[:80]}...")
    result = client.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="30s",
    )
    if result.status and result.status.state == StatementState.FAILED:
        print(f"  FAILED: {result.status.error}")
        return False
    print("  OK")
    return True


def main():
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    catalog = os.environ.get("UC_CATALOG")
    schema = os.environ.get("UC_SCHEMA")

    if not all([host, token, catalog, schema]):
        print("ERROR: Set DATABRICKS_HOST, DATABRICKS_TOKEN, UC_CATALOG, UC_SCHEMA in .env")
        sys.exit(1)

    client = WorkspaceClient(host=host, token=token)
    warehouse_id = find_warehouse(client)

    print(f"\nCreating OTEL table in {catalog}.{schema}...")

    statements = [
        f"USE CATALOG {catalog}",
        f"CREATE SCHEMA IF NOT EXISTS {schema} COMMENT 'OTEL telemetry from Claude Code CLI'",
        f"""CREATE TABLE IF NOT EXISTS {schema}.claude_otel_metrics (
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
)""",
    ]

    for stmt in statements:
        if not execute(client, warehouse_id, stmt):
            sys.exit(1)

    print(f"\nTable created: {catalog}.{schema}.claude_otel_metrics")


if __name__ == "__main__":
    main()
