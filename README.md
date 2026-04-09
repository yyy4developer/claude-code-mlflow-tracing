# Claude Code トレーシング検証

Claude Code の利用ログを Databricks で追跡する2つの方法を検証したプロジェクト。

- **Workspace**: `<WORKSPACE>.cloud.databricks.com`
- **AI Gateway**: `https://<AI_GATEWAY_ID>.ai-gateway.cloud.databricks.com/anthropic`
- **Model**: `databricks-claude-opus-4-6`

## 検証結果サマリー

| Method | 方法 | 結果 |
|--------|------|------|
| 1 | MLflow Tracing (hook) | **成功** — トレース・トークン数・実行時間がMLflow UIで確認可能 |
| 2 | MLflow OTEL | **成功** — metrics/logs/spans 全てUCテーブルに送信成功 |

---

## 前提条件

- Claude Code CLI (`claude`) v2.1.97+
- `uv` (Python パッケージマネージャー)
- Databricks workspace で AI Gateway の Coding Agent Integration が有効
- Method 2: workspace で「OpenTelemetry on Databricks」プレビューが有効

## セットアップ

```bash
cd claude-code-mlflow-tracing
cp .env.example .env  # 認証情報を入力
uv sync
cp .claude/settings.json.example .claude/settings.json  # 設定をコピーして編集
```

---

## Method 1: MLflow Tracing (hook)

Claude Code の Stop hook で `mlflow.claude_code.hooks.stop_hook_handler()` を呼び出し、会話終了時にMLflow実験にトレースを送信する。

### 仕組み

- `mlflow autolog claude .` コマンドで `.claude/settings.json` に hook が注入される
- hook は会話のトランスクリプトを解析し、MLflow trace として記録
- Databricks MLflow UI でトレース履歴、トークン数、実行時間が確認可能

### セットアップ手順

1. `.claude/settings.json` を作成（以下の設定例を参考）
2. hook を注入:
   ```bash
   uv run mlflow autolog claude .
   ```
3. `settings.json` の hook 内の `python` を `.venv/bin/python` に修正（venv の mlflow を使うため）

### settings.json 設定例

```json
{
  "env": {
    "ANTHROPIC_MODEL": "databricks-claude-opus-4-6",
    "ANTHROPIC_BASE_URL": "https://<AI_GATEWAY_ID>.ai-gateway.cloud.databricks.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<DATABRICKS_TOKEN>",
    "ANTHROPIC_CUSTOM_HEADERS": "x-databricks-use-coding-agent-mode: true",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
    "MLFLOW_CLAUDE_TRACING_ENABLED": "true",
    "MLFLOW_TRACKING_URI": "databricks",
    "DATABRICKS_HOST": "https://<WORKSPACE>.cloud.databricks.com",
    "DATABRICKS_TOKEN": "<DATABRICKS_TOKEN>",
    "MLFLOW_EXPERIMENT_NAME": "/Users/<EMAIL>/claude-code-tracing"
  },
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".venv/bin/python -c \"from mlflow.claude_code.hooks import stop_hook_handler; stop_hook_handler()\""
          }
        ]
      }
    ]
  },
  "environment": {
    "MLFLOW_CLAUDE_TRACING_ENABLED": "true",
    "MLFLOW_EXPERIMENT_NAME": "/Users/<EMAIL>/claude-code-tracing"
  }
}
```

### 検証結果

- トレースが MLflow 実験に記録される
- hook の `python` パスが重要: システム Python だとトークン数が誤計測（~50K）、`.venv/bin/python` で正確な値
- 対話モード・非対話モード (`claude -p`) ともに動作
- 記録される情報: Request, Response, Tokens (input/output), Execution time, スパン階層

### 注意点

- hook は `Stop` イベントで発火（会話終了時のみ記録）
- `MLFLOW_EXPERIMENT_NAME` を変更する場合は `mlflow autolog claude .` の再実行が必要
- `env` と `environment` の両方に `MLFLOW_EXPERIMENT_NAME` が必要

---

## Method 2: MLflow OTEL

Claude Code の組み込み OpenTelemetry 機能を使い、metrics/logs/spans を Databricks Unity Catalog の Delta テーブルに送信する。

### 仕組み

- `CLAUDE_CODE_ENABLE_TELEMETRY=1` でテレメトリ有効化
- `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` で spans（トレース）送信を有効化（ベータ機能）
- OTLP exporter で Databricks の OTEL ingest endpoint (`/api/2.0/otel/v1/*`) に送信
- データは Unity Catalog の managed Delta テーブルに格納

### セットアップ手順

1. Databricks MLflow UI から実験を作成（Coding Agent Integration 画面経由で OTEL テーブルが自動生成される）
2. 自動生成される4テーブルを確認:
   - `{experiment_id}_otel_metrics`
   - `{experiment_id}_otel_logs`
   - `{experiment_id}_otel_spans`
   - `{experiment_id}_otel_annotations`
3. `.claude/settings.json` にOTEL設定を追加（以下の設定例を参考）

### settings.json 設定例

```json
{
  "env": {
    "ANTHROPIC_MODEL": "databricks-claude-opus-4-6",
    "ANTHROPIC_BASE_URL": "https://<AI_GATEWAY_ID>.ai-gateway.cloud.databricks.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<DATABRICKS_TOKEN>",
    "ANTHROPIC_CUSTOM_HEADERS": "x-databricks-use-coding-agent-mode: true",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
    "DATABRICKS_HOST": "https://<WORKSPACE>.cloud.databricks.com",
    "DATABRICKS_TOKEN": "<DATABRICKS_TOKEN>",
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "https://<WORKSPACE>.cloud.databricks.com/api/2.0/otel/v1/metrics",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://<WORKSPACE>.cloud.databricks.com/api/2.0/otel/v1/logs",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://<WORKSPACE>.cloud.databricks.com/api/2.0/otel/v1/traces",
    "OTEL_EXPORTER_OTLP_METRICS_HEADERS": "content-type=application/x-protobuf,Authorization=Bearer <TOKEN>,X-Databricks-UC-Table-Name=<CATALOG>.<SCHEMA>.<EXP_ID>_otel_metrics",
    "OTEL_EXPORTER_OTLP_LOGS_HEADERS": "content-type=application/x-protobuf,Authorization=Bearer <TOKEN>,X-Databricks-UC-Table-Name=<CATALOG>.<SCHEMA>.<EXP_ID>_otel_logs",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "content-type=application/x-protobuf,Authorization=Bearer <TOKEN>,X-Databricks-UC-Table-Name=<CATALOG>.<SCHEMA>.<EXP_ID>_otel_spans",
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
    "OTEL_METRIC_EXPORT_INTERVAL": "10000",
    "OTEL_LOGS_EXPORT_INTERVAL": "5000",
    "OTEL_TRACES_EXPORT_INTERVAL": "1000",
    "OTEL_LOG_USER_PROMPTS": "1",
    "OTEL_LOG_TOOL_DETAILS": "1",
    "OTEL_LOG_TOOL_CONTENT": "1"
  }
}
```

### 検証結果

| テーブル | 送信 | 記録内容 |
|----------|------|----------|
| metrics | **成功** | session.count, cost.usage (USD), token.usage (input/output) |
| logs | **成功** | user_prompt (プロンプト内容), api_request (モデル, トークン数, コスト, 所要時間) |
| spans | **成功** | interaction (root), llm_request, tool (Read/Bash等), tool.execution, tool.blocked_on_user |

### スパン階層の例

```
claude_code.interaction (root)
├── claude_code.llm_request (1回目のLLM呼び出し)
├── claude_code.tool (Read: README.md)
│   ├── claude_code.tool.blocked_on_user
│   └── claude_code.tool.execution
├── claude_code.tool (Read: pyproject.toml)
│   ├── claude_code.tool.blocked_on_user
│   └── claude_code.tool.execution
└── claude_code.llm_request (2回目のLLM呼び出し)
```

### spans テーブルに記録されるトークン情報

`llm_request` スパンの attributes に以下が含まれる:

- `input_tokens`, `output_tokens`
- `cache_creation_tokens`, `cache_read_tokens`
- `cost_usd`, `duration_ms`, `ttft_ms`
- `model`, `success`, `attempt`

### 注意点

- **`settings.json` の `env` セクションに `//` コメントを入れるとOTEL環境変数が読み込まれない。純粋なJSONで記述すること**
- OTEL exporter に `console` を追加すると stdout が汚染される。本番では `otlp` のみ推奨
- `OTEL_LOG_USER_PROMPTS=1` でプロンプト内容がログに含まれる（セキュリティ注意）
- OTEL データは送信後 5 分以内に UC テーブルに反映される
- MLflow UI でのトークン数表示は UI 側のマッピングが未対応（データ自体は spans テーブルの attributes に記録済み）
- `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` はベータ機能。将来変更される可能性あり

---

## Bonus: ユーザー定義 AI Gateway エンドポイント

Databricks のシステムエンドポイント（`databricks-claude-opus-4-6`）ではなく、ユーザーが作成した AI Gateway エンドポイントで Claude Code を動かす方法。

### 問題: `adaptive thinking is not supported on this model`

Claude Code はデフォルトで `thinking.type: "adaptive"` を送信する。システムエンドポイントはこれをサポートするが、ユーザー定義エンドポイントは `adaptive` をサポートしていない（`enabled` のみ対応）。

### 解決策

| 方法 | 設定 | thinking |
|------|------|----------|
| A: thinking 完全無効 | `DISABLE_INTERLEAVED_THINKING=1` | 無効（推論品質低下の可能性） |
| B: thinking 有効（固定budget） | `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` + `MAX_THINKING_TOKENS=100000` | 有効（`enabled` モード） |

**方法 B を推奨**。

### settings.json 追加設定

```json
{
  "env": {
    "ANTHROPIC_MODEL": "<your-custom-endpoint-name>",
    "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING": "1",
    "MAX_THINKING_TOKENS": "100000"
  }
}
```

### adaptive vs enabled thinking

| | adaptive（デフォルト） | enabled（固定budget） |
|---|---|---|
| 仕組み | モデルがタスクの複雑さに応じて動的調整 | `MAX_THINKING_TOKENS` で指定した固定budget |
| コスト効率 | 高い | 低い（簡単な質問でもthinkingトークンを多く消費する傾向） |
| 品質 | 最適化済み | `MAX_THINKING_TOKENS` の設定次第 |
| ユーザー定義エンドポイント | 非対応（エラー） | **対応** |

### Claude Code Thinking 関連の環境変数

| 環境変数 | 効果 |
|----------|------|
| `DISABLE_INTERLEAVED_THINKING=1` | interleaved thinking を無効化（thinking 自体を停止） |
| `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` | `adaptive` → `enabled`（固定budget）に切替 |
| `MAX_THINKING_TOKENS=N` | thinking の固定トークン予算（adaptive 無効時のみ有効、`=0` で停止） |
| `CLAUDE_CODE_EFFORT_LEVEL=low/medium/high` | adaptive reasoning の深度制御 |

---

## Inference Table

AI Gateway 経由のリクエストは自動的に inference table に記録される。設定不要。

記録内容: `event_time`, `request`（全文）, `response`（全文）, `latency_ms`, `status_code`, `requester`

---

## プロジェクト構成

```
claude-code-mlflow-tracing/
├── .claude/settings.json          # AI Gateway + tracing 設定（gitignore対象）
├── .env.example                   # 認証情報テンプレート
├── .gitignore
├── pyproject.toml                 # uv: mlflow[databricks], databricks-sdk
├── method1_mlflow/
│   └── verify.py                  # MLflow トレース確認スクリプト
└── README.md
```

## 参考リンク

- [MLflow Tracing for Claude Code](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code)
- [AI Gateway Coding Agent Integration](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-integration-beta)
- [Claude Code Monitoring & Usage](https://code.claude.com/docs/en/monitoring-usage)
- [Claude Code トレース（ベータ）](https://code.claude.com/docs/ja/monitoring-usage#トレース-ベータ)
