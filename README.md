# Claude Code トレーシング検証

Claude Code の利用ログを Databricks で追跡する3つの方法を検証したプロジェクト。

- **Workspace**: `e2-demo-field-eng.cloud.databricks.com`
- **AI Gateway**: `https://1444828305810485.ai-gateway.cloud.databricks.com/anthropic`
- **Model**: `databricks-claude-opus-4-6`

## 検証結果サマリー

| Method | 方法 | 結果 | 備考 |
|--------|------|------|------|
| 1 | MLflow Tracing (hook) | **成功** | トレース・トークン数・実行時間がMLflow UIで確認可能 |
| 2 | OTEL Table | **部分成功** | metrics/logsはUCテーブルに送信成功。spansは組み込みOTELでは送信されない |
| 3 | OTEL → MLflow UI | **未達成** | OTELテーブルのデータがMLflow実験UIのtrace履歴に反映されない |

---

## 前提条件

- Claude Code CLI (`claude`)
- `uv` (Python パッケージマネージャー)
- Databricks workspace で「OpenTelemetry on Databricks」プレビューが有効

## セットアップ

```bash
cd /path/to/claude-code-mlflow-tracing
cp .env.example .env  # 認証情報を入力
uv sync
```

---

## Method 1: MLflow Tracing (hook)

Claude Code の Stop hook で `mlflow.claude_code.hooks.stop_hook_handler()` を呼び出し、会話終了時にMLflow実験にトレースを送信する。

### 仕組み

- `mlflow autolog claude .` コマンドで `.claude/settings.json` に hook が注入される
- hook は会話のトランスクリプトを解析し、MLflow trace として記録
- Databricks MLflow UI でトレース履歴、トークン数、実行時間が確認可能

### セットアップ手順

1. `settings.json` の `env` に以下を設定:

```json
{
  "env": {
    "ANTHROPIC_MODEL": "databricks-claude-opus-4-6",
    "ANTHROPIC_BASE_URL": "https://1444828305810485.ai-gateway.cloud.databricks.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<DATABRICKS_TOKEN>",
    "ANTHROPIC_CUSTOM_HEADERS": "x-databricks-use-coding-agent-mode: true",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
    "MLFLOW_CLAUDE_TRACING_ENABLED": "true",
    "MLFLOW_TRACKING_URI": "databricks",
    "DATABRICKS_HOST": "https://e2-demo-field-eng.cloud.databricks.com",
    "DATABRICKS_TOKEN": "<DATABRICKS_TOKEN>",
    "MLFLOW_EXPERIMENT_NAME": "/Users/<email>/claude-code-tracing"
  }
}
```

2. hook を注入:

```bash
uv run mlflow autolog claude .
```

3. `settings.json` の hook 内の `python` を `.venv/bin/python` に修正（venv の mlflow を使うため）

4. テスト:

```bash
claude -p "Say hello"
```

5. 確認:

```bash
uv run python method1_mlflow/verify.py
```

### 検証結果

- **成功**: トレースが MLflow 実験に記録される
- hook の `python` パスが重要: システム Python だとトークン数が ~50K（誤計測）、`.venv/bin/python` だと正確な値
- 対話モードでも動作（会話終了時にトレース送信）
- 実験名を変更すると新しい実験にトレースが記録されないケースあり（`mlflow autolog` 再実行が必要）

### 記録される情報

- Request (ユーザープロンプト)
- Response (Claude の応答)
- Tokens (input/output)
- Execution time
- スパン階層（ツール使用を含む）

### 注意点

- hook は `Stop` イベントで発火するため、会話終了時にのみ記録される
- `MLFLOW_EXPERIMENT_NAME` を変更する場合は `mlflow autolog claude .` の再実行が必要
- `settings.json` の `env` と `environment` の両方に `MLFLOW_EXPERIMENT_NAME` が必要

---

## Method 2: OTEL Table

Claude Code の組み込み OpenTelemetry 機能を使い、メトリクスとログを Databricks Unity Catalog の Delta テーブルに送信する。

### 仕組み

- Claude Code は `CLAUDE_CODE_ENABLE_TELEMETRY=1` で OTEL テレメトリを有効化
- OTLP exporter で Databricks の OTEL ingest endpoint (`/api/2.0/otel/v1/*`) に送信
- データは Unity Catalog の managed Delta テーブルに格納

### テーブル作成

#### 方法A: Databricks UI から作成（推奨）

MLflow 実験を Databricks UI の Coding Agent Integration 画面から作成すると、以下の4テーブルが自動生成される:

- `{experiment_id}_otel_metrics`
- `{experiment_id}_otel_logs`
- `{experiment_id}_otel_spans`
- `{experiment_id}_otel_annotations`

#### 方法B: 手動作成

公式ドキュメントに従い SQL で作成:
https://docs.databricks.com/aws/en/ai-gateway/coding-agent-integration-beta#set-up-opentelemetry-data-collection

```bash
uv run python method2_otel/create_table.py
```

### セットアップ手順

`settings.json` の `env` に以下を追加:

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "https://<workspace>/api/2.0/otel/v1/metrics",
    "OTEL_EXPORTER_OTLP_METRICS_HEADERS": "content-type=application/x-protobuf,Authorization=Bearer <TOKEN>,X-Databricks-UC-Table-Name=<catalog>.<schema>.<table_prefix>_otel_metrics",
    "OTEL_METRIC_EXPORT_INTERVAL": "10000",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://<workspace>/api/2.0/otel/v1/logs",
    "OTEL_EXPORTER_OTLP_LOGS_HEADERS": "content-type=application/x-protobuf,Authorization=Bearer <TOKEN>,X-Databricks-UC-Table-Name=<catalog>.<schema>.<table_prefix>_otel_logs",
    "OTEL_LOGS_EXPORT_INTERVAL": "5000",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://<workspace>/api/2.0/otel/v1/traces",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "content-type=application/x-protobuf,Authorization=Bearer <TOKEN>,X-Databricks-UC-Table-Name=<catalog>.<schema>.<table_prefix>_otel_spans",
    "OTEL_LOG_USER_PROMPTS": "1"
  }
}
```

### 検証結果

| テーブル | 送信 | 備考 |
|----------|------|------|
| metrics | **成功** | session.count, cost.usage, token.usage 等 |
| logs | **成功** | user_prompt, api_request 等（プロンプト内容含む） |
| spans | **失敗** | 組み込み OTEL では spans は送信されない |
| annotations | N/A | OTEL プロトコル外（MLflow 側が管理） |

### 記録されるメトリクス例

- `claude_code.session.count` — セッション数
- `claude_code.cost.usage` — コスト (USD)
- `claude_code.token.usage` — トークン数 (input/output)

### 記録されるログ例

- `claude_code.user_prompt` — ユーザープロンプト内容
- `claude_code.api_request` — API 呼び出し詳細（モデル、トークン数、コスト、所要時間）

### 注意点

- OTEL データは送信後 5 分以内に UC テーブルに反映される
- `OTEL_LOG_USER_PROMPTS=1` でプロンプト内容がログに含まれる（セキュリティ注意）
- spans を送信するにはカスタム hook スクリプトが必要（参考: Glean の「Claude Code OTEL on DBX」ドキュメント）

---

## Method 3: OTEL → MLflow UI (未達成)

### 目標

OTEL テーブルに蓄積されたデータを MLflow 実験 UI の trace 履歴として表示する。

### 検証状況

- Databricks UI から MLflow 実験を作成すると OTEL テーブルが自動生成される
- OTEL metrics/logs は正常にテーブルに送信される
- しかし MLflow 実験 UI の trace タブにデータが**反映されない**
- spans テーブルが空のため、trace 階層が構築できていないことが原因と推測

### 今後の課題

1. **spans の送信**: カスタム hook (`claude-otel-hook.py`) で PreToolUse/PostToolUse/Stop イベントを捕捉し、OTEL spans として送信する必要がある
2. **MLflow trace との連携**: spans テーブルにデータが入れば、MLflow UI で trace 履歴が表示される可能性がある

### カスタム hook (`claude-otel-hook.py`) について

Claude Code の組み込み OTEL では spans が送信されないため、FE メンバー（kuwano さん）がカスタム hook スクリプトを作成している。

- **ドキュメント（MLflow版）**: https://docs.google.com/document/d/1tmXfS0zk7yix_fHRmoVasmaFXX1IpmAmrY8IMS3cks4
- **ドキュメント（OTEL版）**: https://docs.google.com/document/d/1WBkcZiqT3JBIxhA-IsHDHQyc6a77RCcyB8s2ki8M44A

#### 仕組み

`claude-otel-hook.py` は Claude Code の各 hook イベントを捕捉し、OTEL Spans を構築・送信する:

- `UserPromptSubmit` — 新しいプロンプトの開始を記録
- `PreToolUse` — ツール使用開始時刻を記録
- `PostToolUse` — ツール使用結果を子スパンとして蓄積
- `Stop` — 蓄積したスパンをまとめて OTLP で送信

#### スパン階層

```
claude.prompt (root)
├── tool:Read (child)
├── tool:Grep (child)
├── tool:Edit (child)
└── tool:Bash (child)
```

#### 必要パッケージ

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

#### settings.json 設定例

```json
{
  "hooks": {
    "UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": "python3 /path/to/claude-otel-hook.py"}]}],
    "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "python3 /path/to/claude-otel-hook.py"}]}],
    "PostToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "python3 /path/to/claude-otel-hook.py"}]}],
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "python3 /path/to/claude-otel-hook.py"}]}]
  },
  "env": {
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://<workspace>/api/2.0/otel/v1/traces",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "content-type=application/x-protobuf,Authorization=Bearer <TOKEN>,X-Databricks-UC-Table-Name=<catalog>.<schema>.<prefix>_otel_spans"
  }
}
```

**注意**: これは Databricks 公式機能ではなく、FE メンバーが作成したカスタムソリューション。

---

## Bonus: ユーザー定義 AI Gateway エンドポイントの利用

Databricks のシステムエンドポイント（`databricks-claude-opus-4-6`）ではなく、ユーザーが作成した AI Gateway エンドポイントで Claude Code を動かす方法。

### 背景

Databricks AI Gateway では、ユーザーが独自の serving endpoint を作成できる。Claude Code を接続する場合、`ANTHROPIC_BASE_URL` を `/anthropic` パスに向ければ Anthropic Messages API 形式でリクエストが可能。

### 問題: `adaptive thinking is not supported on this model`

Claude Code はデフォルトで `thinking.type: "adaptive"` を送信する。システムエンドポイントはこれをサポートするが、**ユーザー定義エンドポイントは `adaptive` をサポートしていない**（`enabled` のみ対応）。

```bash
# adaptive → エラー
{"thinking": {"type": "adaptive", "budget_tokens": 10000}}
# → "adaptive thinking is not supported on this model"

# enabled → 成功
{"thinking": {"type": "enabled", "budget_tokens": 10000}}
# → 正常に thinking 付きで応答
```

### 解決策

| 方法 | 設定 | thinking |
|------|------|----------|
| A: thinking 完全無効 | `DISABLE_INTERLEAVED_THINKING=1` | 無効（推論品質低下の可能性） |
| B: thinking 有効（固定budget） | `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` + `MAX_THINKING_TOKENS=10000` | 有効（`enabled` モード） |

**方法 B を推奨**。thinking を維持しつつユーザー定義エンドポイントで動作する。

### settings.json 設定例

```json
{
  "env": {
    "ANTHROPIC_MODEL": "your-custom-endpoint-name",
    "ANTHROPIC_BASE_URL": "https://<ai-gateway-id>.ai-gateway.cloud.databricks.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<DATABRICKS_TOKEN>",
    "ANTHROPIC_CUSTOM_HEADERS": "x-databricks-use-coding-agent-mode: true",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
    "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING": "1",
    "MAX_THINKING_TOKENS": "10000"
  }
}
```

### 検証結果

- OpenAI 形式 (`/mlflow/v1/chat/completions`): エンドポイント動作確認 OK
- Anthropic 形式 (`/anthropic/v1/messages`): 動作確認 OK
- `thinking.type: "enabled"`: 動作確認 OK
- `thinking.type: "adaptive"`: **エラー**（ユーザー定義エンドポイント非対応）
- `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` + Claude Code: **動作確認 OK**
- `MAX_THINKING_TOKENS=100000`: 動作確認 OK

### adaptive vs enabled thinking の違い

| | adaptive（デフォルト） | enabled（固定budget） |
|---|---|---|
| **仕組み** | モデルがタスクの複雑さに応じてthinkingトークンを動的調整 | `MAX_THINKING_TOKENS` で指定した固定budget |
| **コスト効率** | 高い（簡単な質問→少ない、複雑→多い） | 低い（簡単な質問でもthinkingトークンを多く消費する傾向） |
| **品質** | 最適化済み（モデルが「どれだけ考えるか」を自動判断） | `MAX_THINKING_TOKENS` の設定次第。小さすぎると推論不足、大きすぎるとトークン浪費 |
| **設定の手間** | 不要 | `MAX_THINKING_TOKENS` の調整が必要 |
| **ユーザー定義エンドポイント** | 非対応（エラー） | **対応** |

**推奨**: `MAX_THINKING_TOKENS` は大きめに設定（例: `100000`）。モデルが不要と判断すれば早めに切り上げるため、常にbudget全体を消費するわけではない。ユーザー定義エンドポイントで `adaptive` が使えない現状では、`enabled` + 大きめの budget が最善の妥協案。

### Claude Code Thinking 関連の環境変数一覧

| 環境変数 | 効果 |
|----------|------|
| `DISABLE_INTERLEAVED_THINKING=1` | interleaved thinking を無効化（thinking 自体を停止） |
| `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` | `adaptive` → `enabled`（固定budget）に切替 |
| `MAX_THINKING_TOKENS=N` | thinking の固定トークン予算（adaptive 無効時のみ有効、`=0` で thinking 停止） |
| `CLAUDE_CODE_EFFORT_LEVEL=low/medium/high` | adaptive reasoning の深度制御 |

### Inference Table

AI Gateway 経由のリクエストは自動的に inference table に記録される。設定不要。

テーブル例: `<catalog>.<schema>.<endpoint>_payload_payload`

記録内容: `event_time`, `request`（全文）, `response`（全文）, `latency_ms`, `status_code`, `requester`

---

## プロジェクト構成

```
claude-code-mlflow-tracing/
├── .claude/settings.json          # AI Gateway + tracing 設定
├── .env.example                   # 認証情報テンプレート
├── .gitignore
├── pyproject.toml                 # uv: mlflow[databricks], databricks-sdk
├── method1_mlflow/
│   └── verify.py                  # MLflow トレース確認スクリプト
├── method2_otel/
│   ├── create_table.sql           # UC テーブル定義
│   ├── create_table.py            # テーブル作成スクリプト
│   └── verify.py                  # UC テーブルデータ確認
├── method3_otel_to_mlflow/
│   └── convert.py                 # OTEL → MLflow 変換（実験的）
└── scripts/
    └── check_prereqs.sh           # 前提条件チェック
```

## 参考リンク

- [MLflow Tracing for Claude Code](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code)
- [AI Gateway Coding Agent Integration](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-integration-beta)
- [Claude Code Monitoring & Usage](https://code.claude.com/docs/en/monitoring-usage)
