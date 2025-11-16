# ローカルテストガイド

このガイドでは、AWS環境へデプロイする前にローカル環境で各Lambda関数をテストする方法を説明します。

## 前提条件

### 必須環境
- Python 3.10以上
- ffmpeg（Preprocessorテスト用）
- OpenAI APIキー

### セットアップ

```bash
# OpenAI APIキーを環境変数に設定
export OPENAI_API_KEY='sk-your-api-key-here'

# ffmpegのインストール確認
ffmpeg -version
```

## テスト環境の構造

ローカルテストでは、S3の構造を `tests/` ディレクトリ内に模倣します:

```
tests/
├── raw-audio/              # アップロード元（テスト音声ファイル配置）
├── raw-audio-ready/        # Preprocessor出力（分割チャンク + metadata）
├── transcripts-chunks/     # Transcribe出力（各チャンクの文字起こし）
├── transcripts/            # Merger出力（統合された文字起こし）
└── outputs/                # Intelligence出力（JSON形式の分析結果）
```

## テストスクリプト

### 1. Preprocessor テスト

**目的**: 音声ファイルの分割処理を検証

```bash
python tools/test_preprocessor_local.py
```

**動作:**
1. `tests/raw-audio/Boyflop.mp3` を読み込み
2. ファイルサイズ・音声長をチェック
3. 25MB/20分超過時に10分チャンクに分割
4. `tests/raw-audio-ready/{file_id}/` に以下を出力:
   - `_metadata.json` - チャンク情報
   - `chunk-000.wav`, `chunk-001.wav`, ... - 分割済みチャンク

**期待される出力例:**
```
============================================================
Preprocessor ローカルテスト
============================================================

[TEST 1] file_id 生成
  ✓ file_id: Boyflop

[TEST 2] 音声長取得
  ✓ Duration: 3838.90 seconds (63.98 minutes)

[TEST 3] ファイルサイズ確認
  ✓ File size: 75.20 MB

[TEST 4] 分割判定
  ✓ Needs splitting: True

[TEST 5] 分割実行 (600秒=10分チャンク)
  ✓ 分割完了: 7 チャンク
    chunk-000.wav: 600.0s, 11.89MB
    chunk-001.wav: 600.0s, 11.49MB
    ...

[TEST 6] メタデータ生成
  ✓ メタデータ保存: tests/raw-audio-ready/Boyflop/_metadata.json

✅ テスト完了!
```

### 2. Transcribe テスト

**目的**: OpenAI API呼び出しによる文字起こしを検証

⚠️ **注意**: OpenAI APIを実際に呼び出すため、**料金が発生**します。

```bash
export OPENAI_API_KEY='your-api-key'
python tools/test_transcribe_local.py
```

**動作:**
1. `tests/raw-audio-ready/{file_id}/chunk-000.wav` を読み込み（Preprocessorで生成）
2. OpenAI `gpt-4o-transcribe-diarize` APIで文字起こし
3. `tests/transcripts-chunks/{file_id}/chunk-000.json` に結果を保存

**期待される出力例:**
```
============================================================
Transcribe ローカルテスト
============================================================

[TEST 1] テストチャンク準備
  ✓ 既存チャンク使用: tests/raw-audio-ready/Boyflop/chunk-000.wav

[TEST 2] OpenAI文字起こし実行
  ⚠️  OpenAI APIを呼び出します（料金が発生）
  ✓ API Key確認済み: sk-proj-...
  ⏳ 文字起こし中（数分かかります）...
  ✓ 文字起こし完了: tests/transcripts-chunks/Boyflop/chunk-000.json

[TEST 3] 結果概要
  テキスト長: 12507 文字
  セグメント数: 343 個

  【最初の3セグメント】
    [0.0s] A: Dude, here's the feeling...
    [1.9s] B: Yeah....
    [2.2s] A: I just size eleven and a half....

✅ Transcribeテスト完了!
```

**コスト見積もり**: 10分のチャンク ≈ $0.36

### 3. Merger テスト

**目的**: 複数チャンクの統合とタイムスタンプ調整を検証

```bash
python tools/test_merger_local.py
```

**動作:**
1. `tests/raw-audio-ready/{file_id}/_metadata.json` を読み込み
2. `tests/transcripts-chunks/{file_id}/` から全チャンクを読み込み
3. タイムスタンプをオフセット調整して統合
4. `tests/transcripts/{file_id}.json` に最終結果を保存

**期待される出力例:**
```
============================================================
Merger ローカルテスト
============================================================

[TEST 1] メタデータ読み込み
  ✓ file_id: Boyflop
  ✓ total_chunks: 7
  ✓ split_required: True

[TEST 2] チャンク文字起こし確認
  ✓ chunk-000.json: 存在
  ✗ chunk-001.json: 未作成
  ...

  利用可能: 1/7 チャンク
  ⚠️  未作成のチャンクがあります
  ℹ️  利用可能なチャンクだけでマージをテストします

[TEST 3] マージ実行
  ⏳ 1 チャンクをマージ中...
  - chunk-000: offset=0.0s, segments=343
  ✓ マージ完了: tests/transcripts/Boyflop.json

[TEST 4] マージ結果概要
  全文テキスト長: 12507 文字
  総セグメント数: 343 個

✅ Mergerテスト完了!
```

### 4. Intelligence テスト

**目的**: GPT-4oによる要約・TODO抽出を検証

⚠️ **注意**: OpenAI APIを実際に呼び出すため、**料金が発生**します。

```bash
export OPENAI_API_KEY='your-api-key'
python tools/test_intelligence_local.py
```

**動作:**
1. `tests/transcripts/{file_id}.json` を読み込み
2. Classifierが選択したプロンプトを使用してGPT-4oで分析・構造化
3. `tests/outputs/{file_id}.json` にJSON形式で保存

**期待される出力例:**
```
============================================================
Intelligence ローカルテスト
============================================================

[TEST 1] 文字起こしファイル確認
  ✓ file_id: Boyflop
  ✓ テキスト長: 12507 文字
  ✓ セグメント数: 343 個

[TEST 2] OpenAI API Key確認
  ✓ API Key確認済み: sk-proj-...

[TEST 3] 分析生成
  ⏳ GPT-4oで分析を生成中（数十秒かかります）...
  ✓ 分析生成完了

[TEST 4] 結果保存
  ✓ JSON保存: tests/outputs/Boyflop.json

============================================================
📋 生成された分析結果
============================================================
【要約】
この会話は「Boy Flop」というポッドキャストのエピソードで...

【参加者】
- Family Jewels: ホストの一人で、音楽制作に関与...

【重要ポイント】
- ジャクソン・ペロッティはアコーディオンのカバー動画を...

【TODO/アクションアイテム】
- 特に具体的なタスクや次のステップは議論されていません...

✅ Intelligenceテスト完了!
```

**コスト見積もり**: 分析生成 ≈ $0.10-0.50

## 連続実行

4つのステージを順番に実行する場合:

```bash
# 1. 分割処理
python tools/test_preprocessor_local.py

# 2. 文字起こし（最初のチャンクのみ）
export OPENAI_API_KEY='your-api-key'
python tools/test_transcribe_local.py

# 3. マージ
python tools/test_merger_local.py

# 4. 要約生成
python tools/test_intelligence_local.py
```

## トラブルシューティング

### ffmpegが見つからない

```
[ERROR] ffmpeg not found
```

→ ffmpegをインストールしてください:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
choco install ffmpeg
```

### OpenAI APIキーエラー

```
❌ エラー: OPENAI_API_KEY 環境変数が設定されていません
```

→ 環境変数を設定してください:
```bash
export OPENAI_API_KEY='sk-your-api-key-here'
```

### Preprocessor実行前にTranscribeテストを実行した場合

```
ℹ️  先にtools/test_preprocessor_local.pyを実行してください
```

→ Preprocessorを先に実行してチャンクを生成してください

### Transcribe未実行でMergerテストを実行した場合

```
⚠️  未作成のチャンクがあります: [0, 1, 2, ...]
```

→ Transcribeテストを実行して文字起こしを生成してください

## 次のステップ

ローカルテストが成功したら:
1. **AWS環境へデプロイ** - README.mdのデプロイ手順を参照
2. **エンドツーエンドテスト** - 実際のS3バケットで全工程を検証
3. **本番運用** - 実際の会議音声でシステムを活用

## テストデータのクリーンアップ

テスト実行後、`tests/` ディレクトリ内のデータを削除する場合:

```bash
# 生成されたデータをすべて削除（元の音声ファイルは保持）
rm -rf tests/raw-audio-ready/*
rm -rf tests/transcripts-chunks/*
rm -rf tests/transcripts/*
rm -rf tests/outputs/*
```
