"""Method 3: Convert OTEL metrics from UC table to MLflow traces.

Reads OTEL metrics from the Unity Catalog Delta table (populated by Method 2)
and creates MLflow runs with logged metrics.

Usage:
    uv run python method3_otel_to_mlflow/convert.py
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState


def query_table(client: WorkspaceClient, warehouse_id: str, sql: str) -> list[dict]:
    result = client.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="60s",
    )
    if result.status and result.status.state == StatementState.FAILED:
        raise RuntimeError(f"Query failed: {result.status.error}")

    schema = result.manifest.schema.columns if result.manifest and result.manifest.schema else []
    col_names = [c.name for c in schema]
    rows = result.result.data_array if result.result else []
    return [dict(zip(col_names, row)) for row in rows]


def main():
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    catalog = os.environ.get("UC_CATALOG")
    schema = os.environ.get("UC_SCHEMA")
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME")

    if not all([host, token, catalog, schema, experiment_name]):
        print("ERROR: Set DATABRICKS_HOST, DATABRICKS_TOKEN, UC_CATALOG, UC_SCHEMA, MLFLOW_EXPERIMENT_NAME in .env")
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

    # Query recent OTEL metrics
    print(f"Reading OTEL metrics from {table}...")
    metrics = query_table(
        client,
        warehouse_id,
        f"""
        SELECT
            metric_name,
            metric_description,
            metric_unit,
            time_unix_nano,
            value_as_double,
            value_as_int,
            attributes,
            resource_attributes
        FROM {table}
        WHERE time_unix_nano >= (unix_timestamp(current_timestamp() - INTERVAL 1 HOUR) * 1000000000)
        ORDER BY time_unix_nano ASC
        LIMIT 1000
        """,
    )

    if not metrics:
        print("No OTEL metrics found in the last hour.")
        print("Run Method 2 first to generate telemetry.")
        return

    print(f"Found {len(metrics)} metric record(s). Converting to MLflow...\n")

    # Set up MLflow
    mlflow.set_tracking_uri("databricks")
    os.environ["DATABRICKS_HOST"] = host
    os.environ["DATABRICKS_TOKEN"] = token
    mlflow.set_experiment(experiment_name)

    # Group metrics by resource_attributes (each unique resource = one session/run)
    sessions: dict[str, list] = {}
    for m in metrics:
        # Use resource_attributes as session key
        resource = str(m.get("resource_attributes", ""))
        sessions.setdefault(resource, []).append(m)

    print(f"Found {len(sessions)} unique session(s).\n")

    for session_key, session_metrics in sessions.items():
        run_name = f"otel-converted-{int(time.time())}"
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.set_tag("source", "otel-uc-table")
            mlflow.set_tag("conversion_method", "method3-otel-to-mlflow")

            # Log each metric
            for m in session_metrics:
                name = m.get("metric_name", "unknown")
                value = m.get("value_as_double")
                if value is None:
                    value = m.get("value_as_int")
                if value is None:
                    continue

                ts_ns = m.get("time_unix_nano", 0)
                ts_ms = int(ts_ns) // 1_000_000 if ts_ns else int(time.time() * 1000)

                try:
                    mlflow.log_metric(
                        key=name.replace(".", "_"),
                        value=float(value),
                        timestamp=ts_ms,
                    )
                except Exception as e:
                    print(f"  Warning: could not log metric '{name}': {e}")

            # Log resource attributes as tags
            attrs = session_metrics[0].get("resource_attributes") or {}
            if isinstance(attrs, dict):
                for k, v in list(attrs.items())[:20]:
                    try:
                        mlflow.set_tag(f"resource.{k}", str(v)[:250])
                    except Exception:
                        pass

            print(f"  Logged run {run.info.run_id} with {len(session_metrics)} metrics")

    print("\nConversion complete. Check the MLflow experiment in Databricks.")


if __name__ == "__main__":
    main()
