"""Method 1: Verify MLflow traces from Claude Code hooks.

Usage:
    uv run python method1_mlflow/verify.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import mlflow
from mlflow.tracking import MlflowClient


def main():
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME")

    if not all([host, token, experiment_name]):
        print("ERROR: Set DATABRICKS_HOST, DATABRICKS_TOKEN, MLFLOW_EXPERIMENT_NAME in .env")
        sys.exit(1)

    mlflow.set_tracking_uri("databricks")
    os.environ["DATABRICKS_HOST"] = host
    os.environ["DATABRICKS_TOKEN"] = token

    client = MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)

    if not experiment:
        print(f"Experiment '{experiment_name}' not found.")
        print("Run 'mlflow autolog claude .' then 'claude -p \"Say hello\"' first.")
        sys.exit(1)

    print(f"Experiment: {experiment.name} (ID: {experiment.experiment_id})")

    # Check for traces
    traces = client.search_traces(
        experiment_ids=[experiment.experiment_id],
        order_by=["timestamp_ms DESC"],
        max_results=5,
    )

    if traces:
        print(f"\nFound {len(traces)} trace(s):")
        for t in traces:
            print(f"  Request ID: {t.info.request_id}")
            print(f"  Status:     {t.info.status}")
            print(f"  Timestamp:  {t.info.timestamp_ms}")
            print()
    else:
        print("\nNo traces found yet. They may still be uploading.")
        print("Check the Databricks MLflow UI manually.")

    # Also check runs
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time DESC"],
        max_results=5,
    )

    if runs:
        print(f"Found {len(runs)} run(s):")
        for r in runs:
            print(f"  Run ID: {r.info.run_id}, Status: {r.info.status}")
    else:
        print("No runs found.")


if __name__ == "__main__":
    main()
