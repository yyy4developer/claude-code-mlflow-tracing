#!/usr/bin/env bash
set -euo pipefail

echo "=== Prerequisites Check ==="

# uv
if ! command -v uv &>/dev/null; then
  echo "ERROR: uv is not installed"
  exit 1
fi
echo "OK: uv $(uv --version)"

# Claude Code
if ! command -v claude &>/dev/null; then
  echo "ERROR: claude CLI is not installed"
  exit 1
fi
echo "OK: claude CLI found"

# .env file
if [[ ! -f .env ]]; then
  echo "ERROR: .env file not found"
  echo "  Run: cp .env.example .env && edit .env with your credentials"
  exit 1
fi
echo "OK: .env file found"

# Check required vars
set -a
source .env
set +a

REQUIRED_VARS=(DATABRICKS_HOST DATABRICKS_TOKEN UC_CATALOG UC_SCHEMA MLFLOW_EXPERIMENT_NAME)
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" || "${!var}" == dapi* && "${#var}" -lt 10 ]]; then
    MISSING+=("$var")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "ERROR: Missing or placeholder values in .env:"
  for v in "${MISSING[@]}"; do
    echo "  - $v"
  done
  exit 1
fi

echo "OK: All required environment variables are set"

# Check settings.local.json
SETTINGS=".claude/settings.local.json"
if [[ ! -f "$SETTINGS" ]]; then
  echo "ERROR: $SETTINGS not found"
  exit 1
fi

if grep -q "TODO_SET" "$SETTINGS"; then
  echo "WARNING: $SETTINGS still has placeholder tokens. Update ANTHROPIC_AUTH_TOKEN."
else
  echo "OK: $SETTINGS configured"
fi

echo ""
echo "=== All checks passed ==="
echo ""
echo "Next steps:"
echo "  Phase A: Update .claude/settings.local.json with your Databricks token"
echo "           Then test: claude -p 'Say hello'  (from this directory)"
echo ""
echo "  Phase B: uv run mlflow autolog claude .    (set up MLflow hooks)"
echo "           claude -p 'Say hello'"
echo "           uv run python method1_mlflow/verify.py"
echo ""
echo "  Phase C: uv run python method2_otel/create_table.py"
echo "           Add OTEL env vars to .claude/settings.local.json"
echo "           claude -p 'Say hello'"
echo "           uv run python method2_otel/verify.py"
echo ""
echo "  Phase D: uv run python method3_otel_to_mlflow/convert.py"
