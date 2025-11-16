# GitHub公開前チェックリスト

このファイルは、リポジトリをGitHubに公開する前の最終確認用です。

## ✅ セキュリティチェック

### 機密情報の除外確認

以下のコマンドを実行して、機密情報が含まれていないことを確認してください：

```bash
# 1. 音声ファイルの確認（test_audio内のサンプルファイルは除く）
find . -type f \( -name "*.wav" -o -name "*.mp3" \) -not -path "./tests/test_audio/*" -not -path "./.git/*"
# → 何も出力されないこと

# 2. zipファイルの確認
find . -name "*.zip" -not -path "./.git/*"
# → 何も出力されないこと

# 3. packageディレクトリの確認
find . -type d -name "package" -not -path "./.git/*"
# → src/transcribe/package, src/intelligence/package, src/classifier/package が表示される（これは正常）

# 4. 環境変数ファイルの確認
find . -name ".env*" -not -name ".env.example" -not -path "./.git/*"
# → 何も出力されないこと

# 5. APIキーや認証情報の確認
grep -r "sk-" . --exclude-dir=.git --exclude-dir=package --exclude="*.md" 2>/dev/null
# → 何も出力されないこと

grep -r "AKIA" . --exclude-dir=.git --exclude-dir=package --exclude="*.md" 2>/dev/null
# → 何も出力されないこと
```

## ✅ .gitignore確認

以下が`.gitignore`に含まれていることを確認：

- [x] `*.wav`, `*.mp3`, `*.m4a`, `*.flac`, `*.ogg`, `*.webm`
- [x] `*.zip`
- [x] `src/transcribe/package/`
- [x] `src/intelligence/package/`
- [x] `src/classifier/package/`
- [x] `*secret*`, `*key*`
- [x] `.env*`
- [x] `config.json`, `credentials.json`
- [x] `__pycache__/`, `*.pyc`

## ✅ README.md確認

- [x] セキュリティ警告が冒頭に記載されている
- [x] セットアップ手順が明確
- [x] AWS事前準備が記載されている
- [x] GitHub公開手順が記載されている
- [x] トラブルシューティングセクションがある

## ✅ 必須ファイルの存在確認

```bash
# 必須ファイルがすべて存在することを確認
ls -la README.md
ls -la .gitignore
ls -la src/preprocessor/lambda_function.py
ls -la src/preprocessor/requirements.txt
ls -la src/transcribe/lambda_function.py
ls -la src/transcribe/requirements.txt
ls -la src/merger/lambda_function.py
ls -la src/merger/requirements.txt
ls -la src/classifier/lambda_function.py
ls -la src/classifier/requirements.txt
ls -la src/intelligence/lambda_function.py
ls -la src/intelligence/requirements.txt
```

## ✅ Git初期化手順

すべての確認が完了したら、以下の手順でGitHubに公開：

```bash
# 1. Gitリポジトリの初期化
git init

# 2. 全ファイルをステージング
git add .

# 3. ステージングされたファイルの確認
git status

# 4. package/ディレクトリやzipファイルが含まれていないことを確認
git status | grep -E "package/|\.zip"
# → 何も出力されないこと

# 5. 初回コミット
git commit -m "Initial commit: Minute Taker serverless transcription system"

# 6. GitHubリポジトリの作成とプッシュ
# オプション1: GitHub CLIを使用
gh repo create minute-taker --public --source=. --remote=origin --push

# オプション2: 手動でリモート追加
# git remote add origin https://github.com/yourusername/minute-taker.git
# git branch -M main
# git push -u origin main
```

## ✅ 公開後の確認

GitHubにプッシュした後：

1. GitHubのリポジトリページで以下を確認：
   - [ ] `package/` ディレクトリが表示されていない
   - [ ] `*.zip` ファイルが表示されていない
   - [ ] `tests/test_audio/` に音声ファイルが表示されていない（.gitkeepのみ）
   - [ ] README.mdが正しく表示される
   - [ ] セキュリティ警告が目立つ位置にある

2. リポジトリ設定の確認：
   - [ ] Public/Private設定が意図通り
   - [ ] ライセンスが設定されている（MIT License）
   - [ ] Descriptionが設定されている

## 📝 推奨される追加設定

公開後に追加することを推奨：

- [ ] GitHub Actionsでの自動テスト（オプション）
- [ ] Issue/PR テンプレート
- [ ] Contributing.md
- [ ] Security Policy (SECURITY.md)
- [ ] Code of Conduct

## ⚠️ 重要な注意事項

- **絶対に公開してはいけないもの**:
  - OpenAI APIキー
  - AWS認証情報（Access Key ID, Secret Access Key）
  - 実際の会議音声ファイル
  - 実際の議事録データ
  - Lambda関数のデプロイメントパッケージ（zipファイル）

- **万が一機密情報をコミットしてしまった場合**:
  1. 直ちにAPIキーを無効化・再生成
  2. `git filter-branch`または`BFG Repo-Cleaner`で履歴から削除
  3. Force pushで履歴を上書き
  4. 新しいAPIキーでSecrets Managerを更新

## 🎉 完了

すべてのチェックが完了したら、このファイルは削除してもOKです：

```bash
git rm GITHUB_CHECKLIST.md
git commit -m "Remove GitHub checklist after verification"
git push
```
