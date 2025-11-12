# ローカルテストガイド

## バッチ処理エンジンのテスト

### 1. 依存関係のインストール

```bash
cd batch-processor
pip install -r requirements.txt
```

### 2. OpenAI APIキーの設定

```bash
export OPENAI_API_KEY=sk-your-api-key-here
```

### 3. テスト用音声ファイルの準備

`tests/test_audio/` ディレクトリに音声ファイルを配置してください。

### 4. ローカル実行テスト

```bash
# Pythonスクリプトとして直接実行
python transcribe.py --local ../tests/test_audio/your_test_file.wav

# 出力ファイルを指定
python transcribe.py --local ../tests/test_audio/your_test_file.wav --output my_output.json
```

### 5. Dockerコンテナでのテスト

```bash
# Dockerイメージをビルド
docker build -t minute-taker-batch .

# コンテナで実行（macOS/Linux）
docker run -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -v $(pwd)/../tests/test_audio:/data \
  minute-taker-batch --local /data/your_test_file.wav

# Windows（PowerShell）の場合
docker run -e OPENAI_API_KEY=$env:OPENAI_API_KEY `
  -v ${PWD}/../tests/test_audio:/data `
  minute-taker-batch --local /data/your_test_file.wav
```

### 6. 出力の確認

- `local_output.json` が生成されます
- JSON内容を確認してください（文字起こしテキスト、タイムスタンプ等）

## トラブルシューティング

### APIキーエラー

```
[ERROR] OPENAI_API_KEY environment variable is not set
```

→ 環境変数 `OPENAI_API_KEY` を設定してください

### ファイルが見つからない

```
[ERROR] File not found: ...
```

→ ファイルパスが正しいか確認してください

### APIエラー

```
[ERROR] Transcription failed: ...
```

→ 以下を確認してください：
- APIキーが有効か
- 音声ファイルのフォーマットが対応しているか（.wav, .mp3等）
- ファイルサイズが適切か（OpenAI APIの制限: 25MB以下推奨）
- ネットワーク接続が正常か

## 次のステップ

ローカルテストが成功したら：
1. AWSインフラのセットアップ（S3, ECS, Lambda等）
2. DockerイメージをECRにプッシュ
3. Lambda関数のデプロイ
4. エンドツーエンドテスト
