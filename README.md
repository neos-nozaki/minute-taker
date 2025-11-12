# 議事録作成システム（Minute Taker）

音声ファイルをS3にアップロードすると、自動で文字起こし・要約・TODO抽出を行うシンプルなサーバーレスシステム

> **⚠️ セキュリティ注意**: このリポジトリにはOpenAI APIキーやAWS認証情報は含まれていません。デプロイ前に必ずAWS Secrets Managerでキーを設定してください。

## システム概要

- **入力**: 会議録音の音声ファイル（.wav, .mp3等）
- **出力**: 文字起こしJSON（話者識別付き）、要約、TODO/アクションアイテム
- **処理方式**: S3トリガー → Lambda（文字起こし） → Lambda（要約生成）
- **主要技術**: Python 3.10+, AWS Lambda, S3, Secrets Manager, OpenAI API

## 主な特徴

- ✅ **話者識別** - `gpt-4o-transcribe-diarize`で「誰が何を話したか」を自動識別
- ✅ **完全サーバーレス** - Fargate/ECS不要、Lambda関数のみで完結
- ✅ **シンプルなインフラ** - S3 + Lambda + Secrets Manager だけ
- ✅ **低コスト** - Lambda無料枠で十分、OpenAI APIのみ課金
- ✅ **Graviton2 (arm64)** - 約20%コスト削減、高性能
- ✅ **柔軟な録音方法** - Teams/Zoom/スマホ等、任意の方法で録音可能
- ✅ **ディレクトリ構造の保持** - `ユーザー名/日付/ファイル名`の階層が自動的に維持
- ✅ **バージョニング対応** - S3バージョニングで上書き・削除からファイルを保護
- ✅ **柔軟な入力形式** - JSON、テキスト、Markdownなど任意のテキスト形式に対応
- ✅ **選べる出力形式** - JSON（デフォルト）、Markdown、または両方を選択可能
- ✅ **プロンプトで出力形式を自由にカスタマイズ** - Lambda: Intelligenceのプロンプトを変更するだけで、要約/TODO/議事録など任意の形式に対応可能

## アーキテクチャ

```
[音声ファイル] 
    ↓ (AWS CLI or 手動アップロード)
[S3: raw-audio/ユーザー名/日付/]
    ↓ (S3 Event Trigger)
[Lambda: Transcribe (arm64)] 
    ↓ (OpenAI gpt-4o-transcribe-diarize API)
    ↓ 話者識別 + タイムスタンプ
[S3: transcripts/ユーザー名/日付/]
    ↓ (S3 Event Trigger)
[Lambda: Intelligence (arm64)]
    ↓ (OpenAI GPT-4o)
    ↓ 要約 + TODO抽出
[S3: summaries/ユーザー名/日付/] + [通知（オプション）]
```

**ディレクトリ構造例:**
```
minute-taker-dev-nozaki/
├── raw-audio/
│   └── nozaki/
│       └── 2025-11-12/
│           ├── meeting-0900.wav
│           └── meeting-1400.mp3
├── transcripts/
│   └── nozaki/
│       └── 2025-11-12/
│           ├── meeting-0900.json
│           └── meeting-1400.json
└── summaries/
    └── nozaki/
        └── 2025-11-12/
            ├── meeting-0900.json  (または .md)
            └── meeting-1400.json  (または .md)
```

**重要なポイント:**
- ディレクトリ構造（ユーザー名/日付）は自動的に保持される
- ファイル名の重複を避けるため、時刻を含めることを推奨（例: `meeting-0900.wav`）
- S3バージョニング有効で、上書きしても過去バージョンを保持

## 前提条件

### ローカル開発環境
- Python 3.10以上
- pip（Pythonパッケージマネージャー）
- AWS CLI（設定済み）
- OpenAI APIキー

### AWS事前準備（必須）

以下のAWSリソースを事前に作成する必要があります：

#### 1. S3バケット
- **バケット名**: 任意（例: `minute-taker-yourname`）
- **リージョン**: 任意（例: `ap-northeast-1`）
- **バージョニング**: 有効化を推奨（ファイルの上書き・削除からの保護）
  ```bash
  aws s3api put-bucket-versioning \
    --bucket your-bucket-name \
    --versioning-configuration Status=Enabled
  ```
- **プレフィックス構造**:
  - `raw-audio/ユーザー名/日付/` - 音声ファイルアップロード先
  - `transcripts/ユーザー名/日付/` - 文字起こしJSON保存先
  - `summaries/ユーザー名/日付/` - 要約JSON/Markdown保存先

#### 2. AWS Secrets Manager
- **シークレット名**: 任意（例: `MinuteTaker/OpenAIKey`）
- **シークレット値**: OpenAI APIキー
- **形式オプション1（JSON）**:
  ```json
  {
    "OPENAI_API_KEY": "sk-your-api-key-here"
  }
  ```
- **形式オプション2（プレーンテキスト）**:
  ```
  sk-your-api-key-here
  ```

#### 3. IAMロール（Lambda用）× 2

**3-1. 文字起こしLambda用ロール**
- ロール名: `MinuteTaker-TranscribeLambdaRole`
- 必要なポリシー:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "s3:GetObject",
          "s3:PutObject"
        ],
        "Resource": [
          "arn:aws:s3:::your-bucket-name/raw-audio/*",
          "arn:aws:s3:::your-bucket-name/transcripts/*"
        ]
      },
      {
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue"
        ],
        "Resource": "arn:aws:secretsmanager:region:account-id:secret:MinuteTaker/OpenAIKey-*"
      },
      {
        "Effect": "Allow",
        "Action": [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        "Resource": "arn:aws:logs:*:*:*"
      }
    ]
  }
  ```

**3-2. 要約Lambda用ロール**
- ロール名: `MinuteTaker-IntelligenceLambdaRole`
- 必要なポリシー:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "s3:GetObject",
          "s3:PutObject"
        ],
        "Resource": [
          "arn:aws:s3:::your-bucket-name/transcripts/*",
          "arn:aws:s3:::your-bucket-name/summaries/*"
        ]
      },
      {
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue"
        ],
        "Resource": "arn:aws:secretsmanager:region:account-id:secret:MinuteTaker/OpenAIKey-*"
      },
      {
        "Effect": "Allow",
        "Action": [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        "Resource": "arn:aws:logs:*:*:*"
      },
      {
        "Effect": "Allow",
        "Action": [
          "sns:Publish"
        ],
        "Resource": "arn:aws:sns:region:account-id:MinuteTaker-Notifications"
      }
    ]
  }
  ```
  ※ SNS通知を使わない場合は最後のSNS権限は不要

#### 4. SNSトピック（オプション）
- **トピック名**: `MinuteTaker-Notifications`
- **用途**: 処理完了時のメール通知
- **サブスクリプション**: 通知先メールアドレスを登録

### AWS事前準備チェックリスト

デプロイ前に以下を確認してください：

- [ ] S3バケット作成済み
- [ ] Secrets ManagerにOpenAI APIキー登録済み
- [ ] IAMロール（文字起こしLambda用）作成済み
- [ ] IAMロール（要約Lambda用）作成済み
- [ ] （オプション）SNSトピック作成済み
- [ ] AWS CLIで対象AWSアカウントに接続できる

### ローカル開発・テスト

Lambda関数をローカルでテストできます：

```bash
cd lambda-transcribe
pip install -r requirements.txt

# 環境変数を設定
export OPENAI_API_KEY=sk-your-api-key

# テスト実行（Pythonスクリプトとして）
python -c "
from lambda_function import transcribe_audio_from_s3, OpenAI
import os
# ローカルテストコード
"
```

## デプロイ手順（AWS Lambda）

### 1. 依存関係のインストール

各Lambda関数のディレクトリで依存関係をインストールします：

```bash
cd lambda-transcribe
pip install -r requirements.txt -t .

cd ../lambda-intelligence
pip install -r requirements.txt -t .
```

### 2. Lambda関数のデプロイ（文字起こし）

```bash
cd lambda-transcribe
zip -r ../function-transcribe.zip .
cd ..

aws lambda create-function \
  --function-name MinuteTaker-Transcribe \
  --runtime python3.10 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/MinuteTaker-TranscribeLambdaRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function-transcribe.zip \
  --timeout 900 \
  --memory-size 512 \
  --environment Variables="{OPENAI_API_KEY_SECRET=MinuteTaker/OpenAIKey,BUCKET_NAME=your-bucket-name}"
```

### 3. Lambda関数のデプロイ（要約）

```bash
cd lambda-intelligence
zip -r ../function-intelligence.zip .
cd ..

aws lambda create-function \
  --function-name MinuteTaker-Intelligence \
  --runtime python3.10 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/MinuteTaker-IntelligenceLambdaRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function-intelligence.zip \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{OPENAI_API_KEY_SECRET=MinuteTaker/OpenAIKey,BUCKET_NAME=your-bucket-name}"
```

### 4. S3イベント通知の設定

**文字起こしLambda用（raw-audio/へのアップロードをトリガー）**

```bash
aws s3api put-bucket-notification-configuration \
  --bucket your-bucket-name \
  --notification-configuration file://s3-notification-transcribe.json
```

`s3-notification-transcribe.json`:
```json
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "arn:aws:lambda:region:account-id:function:MinuteTaker-Transcribe",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "raw-audio/"
            }
          ]
        }
      }
    }
  ]
}
```

**要約Lambda用（transcripts/へのアップロードをトリガー）**

同様に `s3-notification-intelligence.json` を作成し、`LambdaFunctionArn` と `prefix` を調整して適用します。

### 5. Lambda実行権限の付与

S3がLambdaを呼び出せるよう権限を追加：

```bash
aws lambda add-permission \
  --function-name MinuteTaker-Transcribe \
  --statement-id s3-trigger \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::your-bucket-name

aws lambda add-permission \
  --function-name MinuteTaker-Intelligence \
  --statement-id s3-trigger \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::your-bucket-name
```

### AWSへのデプロイ

詳細は `docs/deployment.md` を参照してください（作成予定）。

## ディレクトリ構造

```
minute-taker/
├── lambda-transcribe/    # 文字起こしLambda関数
│   ├── lambda_function.py
│   └── requirements.txt
├── lambda-intelligence/  # 要約・TODO抽出Lambda関数
│   ├── lambda_function.py
│   └── requirements.txt
├── tools/                # アップロード補助ツール等
├── tests/                # テストデータ
├── docs/                 # ドキュメント
├── rough_spec.md         # 要件仕様書
└── TODO.md               # 実装計画
```

## 使い方

### 1. 音声ファイルの準備

任意の方法で会議を録音：
- Teams/Zoom/Google Meetの標準録音機能
- OBS Studio、Audacity等の録音ソフト
- スマートフォンの録音アプリ
- ICレコーダー等

**サポートされている音声形式:** mp3, mp4, mpeg, mpga, m4a, wav, webm, flac, ogg, opus（最大25MB）  
詳細は[OpenAI Audio API公式ドキュメント](https://platform.openai.com/docs/guides/speech-to-text)を参照

### 2. S3へのアップロード

**ディレクトリ構造:**
- `ユーザー名/日付/ファイル名` の形式を推奨
- 同じ日に複数の会議がある場合は、時刻を含めることを推奨（例: `meeting-0900.wav`）

```bash
# AWS CLIでアップロード（ディレクトリ構造を指定）
aws s3 cp meeting_recording.wav s3://your-bucket-name/raw-audio/nozaki/2025-11-12/meeting-0900.wav

# 複数ファイルをまとめてアップロード
aws s3 sync ./recordings/ s3://your-bucket-name/raw-audio/nozaki/2025-11-12/

# または、S3コンソールから手動アップロード
# raw-audio/ユーザー名/日付/ の下にファイルを配置
```

### 3. 処理の自動実行

アップロード後、自動的に以下が実行されます：
1. 文字起こし（**gpt-4o-transcribe-diarize** API）- Lambda関数で実行
   - 話者識別（SPEAKER_00, SPEAKER_01...）
   - セグメント単位のタイムスタンプ
2. 要約生成（GPT-4o）- Lambda関数で実行
3. TODO/アクションアイテム抽出
4. 通知（メール or Webhook）

### 4. 結果の確認

**自動生成されるファイル:**
- ディレクトリ構造が保持されます
- `raw-audio/ユーザー名/日付/file.wav` → `summaries/ユーザー名/日付/file.json`

```bash
# 文字起こし結果（JSON形式、話者識別・タイムスタンプ付き）
aws s3 cp s3://your-bucket-name/transcripts/nozaki/2025-11-12/meeting-0900.json .

# 要約・TODO（JSON形式 - デフォルト）
aws s3 cp s3://your-bucket-name/summaries/nozaki/2025-11-12/meeting-0900.json .

# 要約・TODO（Markdown形式 - OUTPUT_FORMAT=markdown の場合）
aws s3 cp s3://your-bucket-name/summaries/nozaki/2025-11-12/meeting-0900.md .

# ディレクトリ全体をダウンロード
aws s3 sync s3://your-bucket-name/summaries/nozaki/2025-11-12/ ./summaries/
```

## コスト見積もり

### OpenAI API
- **gpt-4o-transcribe-diarize**: $6/1M audio tokens（10分の会議 ≈ $0.36）
  - 話者識別・タイムスタンプ付き
  - 高精度な文字起こしと話者分離
- GPT-4o: 入力$2.50/1M tokens、出力$10/1M tokens（要約生成 ≈ $0.10-0.50）

### AWS
- S3: ほぼ無料（数GB以下）
  - バージョニング有効時は過去バージョンも保存されるため容量増加に注意
- Lambda: 無料枠内で十分（月100万リクエスト、40万GB秒）
  - **Graviton2 (arm64) 採用**で約20%コスト削減
  - 文字起こしLambda: ~1-5分/会議 × 512MB メモリ
  - 要約Lambda: ~10-30秒/会議 × 512MB メモリ

**1会議あたりの推定コスト**: $0.45-1.00（10-60分の会議）
**Graviton2 (arm64) 採用でインフラコスト約20%削減！**
**最新モデルで高精度な話者識別！**

## ベストプラクティス

### ファイル命名規則
- **ディレクトリ構造**: `ユーザー名/日付/ファイル名`
  - 例: `raw-audio/nozaki/2025-11-12/meeting-0900.wav`
- **ファイル名**: 時刻を含めることを推奨
  - 同じ日に複数の会議がある場合の重複を回避
  - 例: `meeting-0900.wav`, `meeting-1400.wav`

### バージョン管理
- S3バージョニングを有効化済み
- ファイルを上書きしても過去バージョンを保持
- 誤削除からの復元が可能

### セキュリティ
- OpenAI APIキーはSecrets Managerで管理
- IAMロールで最小権限の原則を適用
- S3バケットはプライベート設定を推奨

## 出力形式のカスタマイズ

### 出力フォーマットの選択

Lambda Intelligenceの環境変数 `OUTPUT_FORMAT` で出力形式を選択できます：

- **`json`** (デフォルト) - プログラム処理に適した構造化データ
- **`markdown`** - 人間が読みやすいMarkdown形式
- **`both`** - JSON とMarkdown の両方を生成

```bash
# JSON形式（デフォルト）
aws lambda update-function-configuration \
  --function-name MinuteTaker-Intelligence \
  --environment Variables="{OPENAI_API_KEY_SECRET_NAME=MinuteTaker/OpenAIKey,BUCKET_NAME=your-bucket-name,OUTPUT_FORMAT=json}"

# Markdown形式
aws lambda update-function-configuration \
  --function-name MinuteTaker-Intelligence \
  --environment Variables="{OPENAI_API_KEY_SECRET_NAME=MinuteTaker/OpenAIKey,BUCKET_NAME=your-bucket-name,OUTPUT_FORMAT=markdown}"

# 両方
aws lambda update-function-configuration \
  --function-name MinuteTaker-Intelligence \
  --environment Variables="{OPENAI_API_KEY_SECRET_NAME=MinuteTaker/OpenAIKey,BUCKET_NAME=your-bucket-name,OUTPUT_FORMAT=both}"
```

### 入力ファイル形式

`transcripts/` ディレクトリにアップロードするファイルは以下の形式に対応：

- **JSON形式**: `{"text": "会議内容..."}`
- **プレーンテキスト**: `.txt`, `.md` など（拡張子は問わない）
- Lambda関数が自動的に形式を判別して処理

### プロンプトのカスタマイズ

`summaries/` に格納される内容は、`lambda-intelligence/lambda_function.py` の `create_summary_prompt()` 関数を編集するだけで自由に変更できます。

### 現在の実装（デフォルト）

**JSON形式 (`OUTPUT_FORMAT=json`):**
```json
{
  "summary": "会議の要約",
  "key_points": ["ポイント1", "ポイント2"],
  "decisions": ["決定事項1"],
  "action_items": [{"task": "...", "assignee": "...", "deadline": "..."}],
  "next_steps": ["次のステップ1"],
  "metadata": {
    "transcript_s3_key": "transcripts/nozaki/2025-11-12/meeting.txt",
    "generated_at": "2025-11-12T04:36:39.453447",
    "transcript_length": 474
  }
}
```

**Markdown形式 (`OUTPUT_FORMAT=markdown`):**
```markdown
# 議事録

## メタデータ
- **生成日時**: 2025-11-12T04:36:39.453447
- **元ファイル**: `transcripts/nozaki/2025-11-12/meeting.txt`

## 要約
会議の要約内容...

## 重要なポイント
- ポイント1
- ポイント2

## 決定事項
- 決定事項1

## アクションアイテム
- [ ] **タスク1**
  - 担当: 田中さん
  - 期限: 来週金曜日

## 次のステップ
- 次のステップ1
```

### カスタマイズ例

**例1: シンプルな要約のみ**
```python
prompt = f"以下の会議の文字起こしを200-300文字で要約してください。\n\n{text}"
```
→ 要約テキストのみが `summaries/` に保存されます

**例2: TODOリスト形式**
```python
prompt = f"""以下の会議の文字起こしから、アクションアイテムをTODOリスト形式で抽出してください。

{text}

フォーマット:
- [ ] タスク1 (担当: XX, 期限: YYYY/MM/DD)
- [ ] タスク2 (担当: YY, 期限: YYYY/MM/DD)
"""
```
→ チェックボックス付きTODOリストが `summaries/` に保存されます

**例3: Markdown議事録**
```python
prompt = f"""以下の文字起こしからMarkdown形式の議事録を作成してください。

{text}

# 議事録
## 概要
## 主な議論
## 決定事項
## アクションアイテム
"""
```
→ Markdown形式の議事録が `summaries/` に保存されます

### ポイント
- **プロンプトを変えるだけ** - コードのロジック変更は不要
- **GPT-4oの柔軟性** - 自然言語で指示すれば、ほぼ期待通りの形式で返してくれる
- **S3パスは変更不要** - `summaries/` という名前でも、中身は何でもOK
- **同じインフラで多目的に対応** - 用途に応じてプロンプトだけ編集

## トラブルシューティング

### 音声ファイルがアップロードされても処理が始まらない
- CloudWatch LogsでLambda（Transcribe）のログを確認
- S3イベント通知が正しく設定されているか確認

### 文字起こしの品質が悪い
- 音声ファイルの品質を確認（ノイズ、音量）
- 対応フォーマット（.wav, .mp3推奨）を使用

### Lambdaタイムアウトエラー
- 長時間の会議（60分以上）の場合、Lambdaのタイムアウト設定を延長（最大15分）
- メモリを増やすと処理速度が向上（推奨: 1024MB以上）

## ライセンス

MIT License

## セキュリティとプライバシー

### ⚠️ 重要な注意事項

このリポジトリには以下の機密情報は**含まれていません**：
- OpenAI APIキー
- AWS認証情報
- Lambda関数のデプロイメントパッケージ（`package/`ディレクトリ）
- 実際の音声ファイルや議事録データ

### デプロイ前の確認事項

1. **APIキーの管理**
   - OpenAI APIキーは必ずAWS Secrets Managerに保存
   - 環境変数やコードに直接記述しない
   - `.env`ファイルは`.gitignore`に含まれている

2. **AWS認証情報**
   - AWS CLIの認証情報（`~/.aws/credentials`）をコミットしない
   - IAMロールを使用してLambda関数に権限を付与

3. **音声データの取り扱い**
   - 音声ファイルは`.gitignore`で除外されている
   - 実際のデータはS3にのみ保存し、リポジトリにコミットしない

### .gitignoreの確認

以下がGitリポジトリから除外されていることを確認してください：
- `*.wav`, `*.mp3`（音声ファイル）
- `*secret*`, `*key*`（機密情報）
- `lambda-*/package/`（Pythonパッケージ）
- `*.zip`（デプロイメントパッケージ）
- `.env`, `config.json`（設定ファイル）

## GitHubへの公開

### 初回セットアップ

```bash
# Gitリポジトリの初期化
cd /path/to/minute-taker
git init

# .gitignoreの確認（機密情報が除外されていることを確認）
cat .gitignore

# 全ファイルをステージング
git add .

# 初回コミット
git commit -m "Initial commit: Minute Taker serverless system"

# GitHubリポジトリの作成（GitHub CLIを使用する場合）
gh repo create minute-taker --public --source=. --remote=origin

# または、GitHubでリポジトリを作成してからリモートを追加
git remote add origin https://github.com/yourusername/minute-taker.git

# プッシュ
git branch -M main
git push -u origin main
```

### コミット前の確認事項

以下が**含まれていない**ことを必ず確認：
```bash
# 機密情報の確認
git status | grep -E "secret|key|\.env|config\.json"

# パッケージディレクトリの確認
git status | grep "package/"

# 音声ファイルの確認
git status | grep -E "\.wav|\.mp3"

# zipファイルの確認
git status | grep "\.zip"
```

もし上記のコマンドで何か出力された場合は、`.gitignore`を修正してから再度`git add .`を実行してください。

## 開発者向け

- 詳細な実装計画: `TODO.md`
- 要件仕様: `rough_spec.md`
- モデル選択ガイド: `docs/model_selection.md`

## 貢献

プルリクエストは歓迎します。大きな変更の場合は、まずissueを開いて変更内容を議論してください。

## サポート

問題が発生した場合は、GitHubのIssuesセクションで報告してください。
