# 音声コンテンツ分析システム（Minute Taker）

音声ファイルをS3にアップロードすると、自動で文字起こし・分析・構造化を行うサーバーレスシステム

> **⚠️ セキュリティ注意**: このリポジトリにはOpenAI APIキーやAWS認証情報は含まれていません。デプロイ前に必ずAWS Secrets Managerでキーを設定してください。

## システム概要

- **入力**: 音声ファイル（会議、面接、講義、日常会話など）
- **出力**: 文字起こしJSON（話者識別付き）、分析結果（JSON/Markdown形式）
- **処理方式**: S3トリガー → 4つのLambda関数による段階的処理
- **主要技術**: Python 3.10+, AWS Lambda, S3, Secrets Manager, OpenAI API, ffmpeg

## 主な特徴

- ✅ **話者識別** - `gpt-4o-transcribe-diarize`で「誰が何を話したか」を自動識別
- ✅ **大容量ファイル対応** - 25MB/20分超過時にffmpegで自動分割
- ✅ **並列同時実行** - 分割された音声チャンクを複数Lambdaで同時文字起こし、処理時間を大幅短縮
- ✅ **統一的なチャンク処理** - 非分割ファイルもチャンク数1として統一処理
- ✅ **アカウント・日付別管理** - `{account_name}/YYYY-MM-DD/` 構造で複数ユーザー・日付管理
- ✅ **完全サーバーレス** - Fargate/ECS不要、Lambda関数のみで完結
- ✅ **シンプルなインフラ** - S3 + Lambda + Secrets Manager だけ
- ✅ **低コスト** - Lambda無料枠で十分、OpenAI APIのみ課金
- ✅ **JSON形式出力** - 構造化されたデータで他システムとの連携が容易
- ✅ **柔軟なプロンプト管理** - S3に配置したプロンプトテンプレートでカスタマイズ可能
- ✅ **自動コンテンツ分類** - GPT-4o-miniが文字起こしから最適なプロンプトを自動選択
- ✅ **多様なコンテンツ対応** - 会議・面接・講義・日常会話など、用途別プロンプトを自動判定
- ✅ **arm64最適化** - ClassifierとIntelligenceをarm64アーキテクチャで高速実行
- ✅ **5段階パイプライン** - Preprocessor → Transcribe → Merger → Classifier → Intelligence

## アーキテクチャ

```
[ユーザー]
    ↓ アップロード
raw-audio/{account_name}/YYYY-MM-DD/{filename}.wav
    ↓ S3 Event Trigger
[Lambda: Preprocessor]
    - ファイルサイズ・長さチェック
    - 25MB/20分超過時に分割
    - file_id 生成（= ファイル名から拡張子を除いたもの）
    - _metadata.json 作成
    ↓
raw-audio-ready/{account_name}/YYYY-MM-DD/{file_id}/
    ├── _metadata.json  (total_chunks: 1 or N)
    ├── chunk-000.wav   (非分割でも chunk-000)
    ├── chunk-001.wav   (分割時のみ)
    └── chunk-002.wav
    ↓ S3 Event Trigger (各チャンク)
[Lambda: Transcribe] (並列実行、arm64)
    - OpenAI gpt-4o-transcribe-diarize
    - 各チャンク個別に文字起こし
    ↓
transcripts-chunks/{account_name}/YYYY-MM-DD/{file_id}/
    ├── chunk-000.json
    ├── chunk-001.json
    └── chunk-002.json
    ↓ S3 Event Trigger (各チャンク完了時)
[Lambda: Merger] (Python 3.12)
    - 全チャンク完了を待機（冪等）
    - タイムスタンプ調整して統合
    ↓
transcripts/{account_name}/YYYY-MM-DD/{file_id}.json
    ↓ S3 Event Trigger
[Lambda: Classifier] (arm64、GPT-4o-mini)
    - 文字起こし内容を分析
    - 最適なプロンプトテンプレートを自動選択
    - 判断理由と信頼度を記録
    ↓
classifications/{account_name}/YYYY-MM-DD/{file_id}.json
    ↓ S3 Event Trigger
[Lambda: Intelligence] (arm64、GPT-4o)
    - Classifierが選択したプロンプトで分析実行
    - 構造化されたJSON形式で出力
    ↓
outputs/{account_name}/YYYY-MM-DD/{file_id}.json
```

## S3ディレクトリ構造

```
minute-taker-bucket/
├── prompts/                                 ← プロンプトテンプレート
│   ├── classifier/
│   │   └── judge.md                         ← 分類判断用プロンプト
│   └── intelligence/
│       ├── meeting.md                       ← 会議用
│       ├── interview.md                     ← 面接用
│       ├── lecture.md                       ← 講義用
│       └── casual_conversation.md           ← 日常会話用
│
├── raw-audio/
│   └── {account_name}/                      ← アカウント名ディレクトリ
│       └── YYYY-MM-DD/                      ← 日付ディレクトリ
│           ├── meeting-audio.wav            ← ユーザーがアップロード
│           ├── interview-recording.wav
│           └── lecture-session.mp3
│
├── raw-audio-ready/
│   └── {account_name}/
│       └── YYYY-MM-DD/
│           ├── meeting-audio/
│           │   ├── _metadata.json           ← 制御ファイル
│           │   └── chunk-000.wav            ← 非分割時も chunk-000
│           ├── interview-recording/
│           │   ├── _metadata.json
│           │   ├── chunk-000.wav            ← 分割時
│           │   ├── chunk-001.wav
│           │   └── chunk-002.wav
│           └── lecture-session/
│               ├── _metadata.json
│               └── chunk-000.wav
│
├── transcripts-chunks/
│   └── {account_name}/
│       └── YYYY-MM-DD/
│           ├── meeting-audio/
│           │   └── chunk-000.json
│           ├── interview-recording/
│           │   ├── chunk-000.json
│           │   ├── chunk-001.json
│           │   └── chunk-002.json
│           └── lecture-session/
│               └── chunk-000.json
│
├── transcripts/
│   └── {account_name}/
│       └── YYYY-MM-DD/
│           ├── meeting-audio.json           ← 最終的な文字起こし
│           ├── interview-recording.json
│           └── lecture-session.json
│
├── classifications/                         ← 分類結果
│   └── {account_name}/
│       └── YYYY-MM-DD/
│           ├── meeting-audio.json
│           ├── interview-recording.json
│           └── lecture-session.json
│
└── outputs/                                 ← 最終分析結果（JSON形式）
    └── {account_name}/
        └── YYYY-MM-DD/
            ├── meeting-audio.json
            ├── interview-recording.json
            └── lecture-session.json
```

**重要なポイント:**
- アカウント名/日付/ファイル名の階層構造で整理
- すべてのファイルが`{account_name}/YYYY-MM-DD/{file_id}`で管理
- 非分割ファイルも「チャンク数1」として統一処理
- **Classifier層がGPT-4o-miniで自動的に最適なプロンプトを選択**
- **分類結果は`classifications/`に永続化され、デバッグ・監査が可能**
- **プロンプトテンプレートをS3で管理し、新しいテンプレート追加で自動認識**
- **会議・面接・講義・日常会話など多様なコンテンツに自動対応**
- **arm64アーキテクチャでClassifierとIntelligenceを高速実行**

## プロジェクト構造

```
minute-taker/
├── src/                      # Lambda関数ソース（Lambda非依存）
│   ├── preprocessor/         # 1. 前処理・分割
│   │   ├── lambda_function.py
│   │   └── requirements.txt
│   ├── transcribe/           # 2. 文字起こし
│   │   ├── lambda_function.py
│   │   └── requirements.txt
│   ├── merger/               # 3. チャンク統合
│   │   ├── lambda_function.py
│   │   └── requirements.txt
│   ├── classifier/           # 4. プロンプト自動選択（新規）
│   │   ├── lambda_function.py
│   │   └── requirements.txt
│   └── intelligence/         # 5. 分析・構造化
│       ├── lambda_function.py
│       └── requirements.txt
│
├── prompts/                  # プロンプトテンプレート（S3にアップロード）
│   ├── classifier/
│   │   └── judge.md
│   └── intelligence/
│       ├── meeting.md
│       ├── interview.md
│       ├── lecture.md
│       └── casual_conversation.md
│
├── tests/                    # テスト環境（S3構造を模倣）
│   ├── raw-audio/
│   ├── raw-audio-ready/
│   ├── transcripts-chunks/
│   ├── transcripts/
│   ├── classifications/
│   └── outputs/
│
├── tools/                    # ローカルテストスクリプト
│   ├── test_preprocessor_local.py
│   ├── test_transcribe_local.py
│   ├── test_merger_local.py
│   ├── test_intelligence_local.py
│   └── upload_to_s3.py
│
├── docs/                     # ドキュメント
│   ├── local_testing.md
│   └── model_selection.md
│
└── rough_spec.md             # 要件仕様書
```

## metadata.jsonの例

### 非分割時（チャンク数1）
```json
{
  "file_id": "meeting-audio",
  "account_name": "nozaki",
  "date": "2025-11-17",
  "original_file": "raw-audio/nozaki/2025-11-17/meeting-audio.wav",
  "original_size_bytes": 20971520,
  "original_duration_sec": 900,
  "total_chunks": 1,
  "split_required": false,
  "created_at": "2025-11-17T09:00:00Z",
  "chunks": [
    {
      "index": 0,
      "file": "chunk-000.wav",
      "start_time_sec": 0,
      "end_time_sec": 900,
      "size_bytes": 20971520
    }
  ]
}
```

### 分割時（チャンク数3）
```json
{
  "file_id": "interview-recording",
  "account_name": "tanaka",
  "date": "2025-11-18",
  "original_file": "raw-audio/tanaka/2025-11-18/interview-recording.wav",
  "original_size_bytes": 104857600,
  "original_duration_sec": 3600,
  "total_chunks": 3,
  "split_required": true,
  "created_at": "2025-11-18T14:00:00Z",
  "chunks": [
    {
      "index": 0,
      "file": "chunk-000.wav",
      "start_time_sec": 0,
      "end_time_sec": 1200,
      "size_bytes": 34952533
    },
    {
      "index": 1,
      "file": "chunk-001.wav",
      "start_time_sec": 1200,
      "end_time_sec": 2400,
      "size_bytes": 34952533
    },
    {
      "index": 2,
      "file": "chunk-002.wav",
      "start_time_sec": 2400,
      "end_time_sec": 3600,
      "size_bytes": 34952534
    }
  ]
}
```

## 前提条件

### ローカル開発環境
- Python 3.10以上
- pip（Pythonパッケージマネージャー）
- AWS CLI（設定済み）
- OpenAI APIキー
- **ffmpeg** （ローカルテスト用）

### AWS事前準備

#### 1. S3バケット
- **バケット名**: 任意（例: `minute-taker-yourname`）
- **リージョン**: 任意（例: `ap-northeast-1`）
- **バージョニング**: 有効化を推奨

#### 2. AWS Secrets Manager
- **シークレット名**: 任意（例: `MinuteTaker/OpenAIKey`）
- **シークレット値**: OpenAI APIキー
- **形式**: JSON `{"OPENAI_API_KEY": "sk-..."}` またはプレーンテキスト

#### 3. IAMロール（Lambda用）× 4
各Lambda関数用のロールを作成し、必要な権限を付与：
- S3読み書き権限（各関数が必要とするプレフィックスのみ）
- Secrets Manager読み取り権限
- CloudWatch Logs書き込み権限

## ローカルテスト

詳細は `docs/local_testing.md` を参照。

```bash
# 1. Preprocessorテスト（分割処理確認）
python tools/test_preprocessor_local.py

# 2. Transcribeテスト（OpenAI API呼び出し、料金発生）
export OPENAI_API_KEY='your-api-key'
python tools/test_transcribe_local.py

# 3. Mergerテスト（チャンク統合）
python tools/test_merger_local.py

# 4. Intelligenceテスト（要約生成、OpenAI API呼び出し）
python tools/test_intelligence_local.py
```

テスト結果は `tests/` ディレクトリに保存されます。

## デプロイ手順

### 1. ffmpeg Lambda Layerの作成

Preprocessor LambdaでffmpegとffprobeWを使用するため、Lambda Layerを作成します。

```bash
# ffmpeg静的ビルドをダウンロード（Amazon Linux 2互換）
mkdir -p lambda-layer-ffmpeg/bin
cd lambda-layer-ffmpeg/bin
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar xf ffmpeg-release-amd64-static.tar.xz
cp ffmpeg-*-amd64-static/ffmpeg .
cp ffmpeg-*-amd64-static/ffprobe .
cd ..

# Layerパッケージ作成
mkdir -p ffmpeg-layer/bin
cp bin/ffmpeg bin/ffprobe ffmpeg-layer/bin/
cd ffmpeg-layer
zip -r ../ffmpeg-layer.zip .
cd ..

# Lambda Layerをデプロイ
aws lambda publish-layer-version \
  --layer-name ffmpeg \
  --zip-file fileb://ffmpeg-layer.zip \
  --compatible-runtimes python3.10 \
  --compatible-architectures x86_64
```

### 2. Lambda関数のデプロイ

#### 2-1. Preprocessor Lambda

```bash
cd src/preprocessor
pip install -r requirements.txt -t package/
cd package
zip -r ../function-preprocessor.zip .
cd ..
zip -g function-preprocessor.zip lambda_function.py
cd ../..

aws lambda create-function \
  --function-name MinuteTaker-Preprocessor \
  --runtime python3.10 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/MinuteTaker-PreprocessorRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://src/preprocessor/function-preprocessor.zip \
  --timeout 900 \
  --memory-size 1024 \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:ffmpeg:VERSION
```

#### 2-2. Transcribe Lambda

```bash
cd src/transcribe
pip install -r requirements.txt -t package/
cd package
zip -r ../function-transcribe.zip .
cd ..
zip -g function-transcribe.zip lambda_function.py
cd ../..

aws lambda create-function \
  --function-name MinuteTaker-Transcribe \
  --runtime python3.10 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/MinuteTaker-TranscribeRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://src/transcribe/function-transcribe.zip \
  --timeout 900 \
  --memory-size 512 \
  --environment Variables="{OPENAI_API_KEY_SECRET_NAME=MinuteTaker/OpenAIKey}"
```

#### 2-3. Merger Lambda

```bash
cd src/merger
pip install -r requirements.txt -t package/
cd package
zip -r ../function-merger.zip .
cd ..
zip -g function-merger.zip lambda_function.py
cd ../..

aws lambda create-function \
  --function-name MinuteTaker-Merger \
  --runtime python3.10 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/MinuteTaker-MergerRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://src/merger/function-merger.zip \
  --timeout 300 \
  --memory-size 512
```

#### 2-4. Classifier Lambda (arm64)

```bash
# Dockerを使用してarm64向けにビルド
cd src/classifier

# Dockerコンテナ内でビルド
docker run --rm \
  --platform linux/arm64 \
  -v "$PWD":/var/task \
  -v "$PWD/../../deploy":/output \
  public.ecr.aws/lambda/python:3.10 \
  bash -c "pip install -r requirements.txt -t /var/task/package && \
           cd /var/task/package && \
           zip -r /output/function-classifier-arm64.zip . && \
           cd /var/task && \
           zip -g /output/function-classifier-arm64.zip lambda_function.py"

cd ../..

aws lambda create-function \
  --function-name MinuteTaker-Classifier \
  --runtime python3.10 \
  --architectures arm64 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/MinuteTaker-ClassifierRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://deploy/function-classifier-arm64.zip \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{OPENAI_API_KEY_SECRET_NAME=MinuteTaker/OpenAIKey,PROMPT_BUCKET=your-bucket-name}"
```

#### 2-5. Intelligence Lambda (arm64)

```bash
# Dockerを使用してarm64向けにビルド
cd src/intelligence

# Dockerコンテナ内でビルド
docker run --rm \
  --platform linux/arm64 \
  -v "$PWD":/var/task \
  -v "$PWD/../../deploy":/output \
  public.ecr.aws/lambda/python:3.10 \
  bash -c "pip install -r requirements.txt -t /var/task/package && \
           cd /var/task/package && \
           zip -r /output/function-intelligence-arm64.zip . && \
           cd /var/task && \
           zip -g /output/function-intelligence-arm64.zip lambda_function.py"

cd ../..

aws lambda create-function \
  --function-name MinuteTaker-Intelligence \
  --runtime python3.10 \
  --architectures arm64 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/MinuteTaker-IntelligenceRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://deploy/function-intelligence-arm64.zip \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{OPENAI_API_KEY_SECRET_NAME=MinuteTaker/OpenAIKey,PROMPT_BUCKET=your-bucket-name}"
```

### 3. プロンプトテンプレートのアップロード

```bash
# プロンプトテンプレートをS3にアップロード
aws s3 sync prompts/ s3://your-bucket-name/prompts/ --exclude "*" --include "*.md"
```

### 4. S3イベント通知の設定

```json
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "trigger-preprocessor",
      "LambdaFunctionArn": "arn:aws:lambda:REGION:ACCOUNT:function:MinuteTaker-Preprocessor",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "raw-audio/"}
          ]
        }
      }
    },
    {
      "Id": "trigger-transcribe",
      "LambdaFunctionArn": "arn:aws:lambda:REGION:ACCOUNT:function:MinuteTaker-Transcribe",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "raw-audio-ready/"},
            {"Name": "suffix", "Value": ".wav"}
          ]
        }
      }
    },
    {
      "Id": "trigger-merger",
      "LambdaFunctionArn": "arn:aws:lambda:REGION:ACCOUNT:function:MinuteTaker-Merger",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "transcripts-chunks/"},
            {"Name": "suffix", "Value": ".json"}
          ]
        }
      }
    },
    {
      "Id": "trigger-classifier",
      "LambdaFunctionArn": "arn:aws:lambda:REGION:ACCOUNT:function:MinuteTaker-Classifier",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "transcripts/"},
            {"Name": "suffix", "Value": ".json"}
          ]
        }
      }
    },
    {
      "Id": "trigger-intelligence",
      "LambdaFunctionArn": "arn:aws:lambda:REGION:ACCOUNT:function:MinuteTaker-Intelligence",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "classifications/"},
            {"Name": "suffix", "Value": ".json"}
          ]
        }
      }
    }
  ]
}
```

### 5. Lambda実行権限の付与

```bash
aws lambda add-permission \
  --function-name MinuteTaker-Preprocessor \
  --statement-id s3-trigger \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::your-bucket-name

# 他の4つのLambda関数にも同様に実行
# MinuteTaker-Transcribe, MinuteTaker-Merger, MinuteTaker-Classifier, MinuteTaker-Intelligence
```

## 使い方

### 1. 音声ファイルのアップロード

```bash
# AWS CLIでアップロード（アカウント名/日付/ファイル名 の構造）
aws s3 cp standup.wav s3://your-bucket-name/raw-audio/nozaki/2025-11-17/meeting-audio.wav

# 大容量ファイルも気にせずアップロード（自動分割される）
aws s3 cp interview.wav s3://your-bucket-name/raw-audio/tanaka/2025-11-18/interview-recording.wav

# 講義録音など、会議以外にも対応
aws s3 cp lecture.mp3 s3://your-bucket-name/raw-audio/yamada/2025-11-19/lecture-session.mp3
```

### 2. 処理の自動実行

アップロード後、自動的に以下が実行されます：

1. **Preprocessor**: ファイルサイズ・長さチェック → 必要なら分割
2. **Transcribe**: 各チャンクを並列に文字起こし
3. **Merger**: 全チャンク完了後、タイムスタンプ調整して統合
4. **Intelligence**: S3からプロンプト取得 → GPT-4oで分析・構造化

### 2. 結果の確認

```bash
# 最終的な文字起こし
aws s3 cp s3://your-bucket-name/transcripts/nozaki/2025-11-17/meeting-audio.json .

# 分類結果
aws s3 cp s3://your-bucket-name/classifications/nozaki/2025-11-17/meeting-audio.json .

# 最終分析結果
aws s3 cp s3://your-bucket-name/outputs/nozaki/2025-11-17/meeting-audio.json .

# 面接の文字起こし
aws s3 cp s3://your-bucket-name/transcripts/tanaka/2025-11-18/interview-recording.json .
```

## 出力形式のカスタマイズ

### 出力フォーマット

Intelligence Lambdaは**JSON形式のみ**で構造化された分析結果を出力します。これにより他システムとの連携が容易になります。

**出力例**:
```json
{
  "summary": "会議の概要...",
  "participants": ["Aさん", "Bさん"],
  "topics_discussed": ["トピック1", "トピック2"],
  "action_items": [{"task": "...", "assignee": "..."}],
  "metadata": {
    "file_id": "meeting-audio",
    "account_name": "nozaki",
    "date": "2025-11-17",
    "classification": "meeting",
    "confidence": 0.95
  }
}
```

### プロンプトテンプレートの自動選択

Classifier Lambda（**arm64アーキテクチャで高速実行**）が文字起こしの内容を分析し、最適なプロンプトを自動選択します：

- **`prompts/intelligence/meeting.md`** (デフォルト) - 会議の議事録作成
- **`prompts/intelligence/interview.md`** - 面接・インタビュー分析
- **`prompts/intelligence/lecture.md`** - 講義・セミナー分析
- **`prompts/intelligence/casual_conversation.md`** - 日常会話の記録

分類結果は `classifications/{file_id}.json` に保存されます。

### プロンプトのカスタマイズ

`outputs/` に格納される内容は、S3の `prompts/intelligence/` ディレクトリに配置したMarkdownテンプレートで自由に変更できます。テンプレート内で `{transcript_text}` が文字起こしテキストに置換されます。

**カスタマイズ例:**

```python
# シンプルな要約のみ
以下の音声コンテンツを200-300文字で要約してください。

{transcript_text}

# TODOリスト形式
以下の会議からアクションアイテムをJSON形式で抽出してください。

{transcript_text}

出力形式:
{
  "action_items": [
    {"task": "...", "assignee": "...", "deadline": "..."}
  ]
}

# カスタムMarkdown形式
以下からMarkdown形式のレポートを作成してください:

{transcript_text}

# レポート
## 概要
## 主なポイント
## 次のステップ
```

## トラブルシューティング

### Preprocessorでffmpegエラー

- Lambda Layerが正しくアタッチされているか確認
- ffmpegのパスが正しいか確認（`/opt/bin/ffmpeg`）

### Mergerが実行されない

- CloudWatch Logsで「Waiting for all chunks」メッセージを確認
- すべてのチャンクのTranscribeが完了しているか確認

### タイムスタンプがずれる

- metadata.jsonの`start_time_sec`が正しいか確認
- Mergerがタイムオフセットを正しく適用しているか確認

## コスト見積もり

### OpenAI API
- **gpt-4o-transcribe-diarize**: $6/1M audio tokens
  - 10分の音声 ≈ $0.36
  - 60分の音声（6チャンク） ≈ $2.16
- **GPT-4o**: 入力$2.50/1M tokens、出力$10/1M tokens
  - 分析生成 ≈ $0.10-0.50

### AWS
- **S3**: ほぼ無料（数GB以下）
- **Lambda**: 無料枠内で十分
  - Preprocessor: 分割時のみ実行時間増
  - Transcribe: チャンク数 × 実行時間
  - Merger: 軽量（数秒）
  - Intelligence: 軽量（数秒）

**1ファイルあたりの推定コスト**: $0.50-2.50（10-60分の音声）

## ライセンス

MIT License

## 貢献

プルリクエストは歓迎します。大きな変更の場合は、まずissueを開いて変更内容を議論してください。

## サポート

問題が発生した場合は、GitHubのIssuesセクションで報告してください。
