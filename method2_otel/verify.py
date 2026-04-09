"""Method 2: Verify OTEL metrics data in Unity Catalog table.

Usage:
    uv run python method2_otel/verify.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState


def main():
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    catalog = os.environ.get("UC_CATALOG")
    schema = os.environ.get("UC_SCHEMA")

    if not all([host, token, catalog, schema]):
        print("ERROR: Set DATABRICKS_HOST, DATABRICKS_TOKEN, UC_CATALOG, UC_SCHEMA in .env")
        sys.exit(1)

    client = WorkspaceClient(host=host, token=token)

    # Find warehouse
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        warehouses = list(client.warehouses.list())
        running = [w for w in warehouses if w.state and "RUNNING" in str(w.state)]
        if not running:
            print("ERROR: No running SQL warehouse found")
            sys.exit(1)
        warehouse_id = running[0].id

    table = f"{catalog}.{schema}.claude_otel_metrics"
    print(f"Checking table: {table}\n")

    # Count rows
    result = client.statement_execution.execute_statement(
        statement=f"SELECT COUNT(*) as cnt FROM {table}",
        warehouse_id=warehouse_id,
        wait_timeout="30s",
    )
    if result.status and result.status.state == StatementState.FAILED:
        print(f"ERROR: {result.status.error}")
        sys.exit(1)

    rows = result.result.data_array if result.result else []
    cnt = int(rows[0][0]) if rows else 0

    if cnt == 0:
        print("WARNING: Table exists but is empty.")
        print("OTEL data may not have arrived yet (wait 2-3 minutes after running Claude Code).")
        return

    print(f"SUCCESS: {cnt} row(s) in table\n")

    # Show recent metrics
    result = client.statement_execution.execute_statement(
        statement=f"""
        SELECT metric_name, COUNT(*) as cnt,
               MIN(from_unixtime(time_unix_nano / 1000000000)) as earliest,
               MAX(from_unixtime(time_unix_nano / 1000000000)) as latest
        FROM {table}
        GROUP BY metric_name
        ORDER BY cnt DESC
        LIMIT 20
        """,
        warehouse_id=warehouse_id,
        wait_timeout="30s",
    )

    if result.result and result.result.data_array:
        print("Metrics summary:")
        print(f"  {'Metric Name':<50} {'Count':>6}  {'Earliest':<20} {'Latest':<20}")
        print("  " + "-" * 100)
        for row in result.result.data_array:
            print(f"  {row[0]:<50} {row[1]:>6}  {row[2]:<20} {row[3]:<20}")


if __name__ == "__main__":
    main()
