# OpenAI Audio API モデル選択ガイド

## 利用可能なモデル（2025年11月時点）

### Speech-to-Text（文字起こし）用モデル

| モデル名                      | 特徴           | 用途               | 価格                  |
|-------------------------------|----------------|--------------------|-----------------------|
| **gpt-4o-transcribe-diarize** | 話者識別付き   | バッチ処理・議事録 | $6/1M tokens          |
| gpt-4o-transcribe             | 標準文字起こし | 一般的な文字起こし | $2.5/1M tokens (入力) |
| gpt-4o-mini-transcribe        | 軽量版         | コスト重視         | 未公開（安価）        |

## 本プロジェクトでの選択

### ✅ 採用モデル: `gpt-4o-transcribe-diarize`

**理由:**
1. **話者識別機能** - 「誰が何を話したか」を自動識別
   - 将来的な拡張性
   - 議事録の質向上
2. **HTTPリクエスト専用** - バッチ処理に最適
3. **最新のASRモデル** - 高精度な文字起こし
4. **タイムスタンプ付き** - セグメント単位で時間情報

**レスポンス形式:**
```json
{
  "text": "会議全体のテキスト",
  "segments": [
    {
      "id": 0,
      "seek": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "こんにちは、今日は...",
      "speaker": "SPEAKER_00",  // 話者識別
      "temperature": 0.0,
      "avg_logprob": -0.3,
      "compression_ratio": 1.2,
      "no_speech_prob": 0.01
    }
  ],
  "language": "ja",
  "duration": 120.5
}
```

## 他のモデルとの比較

### gpt-4o-transcribe（話者識別なし）
- 単純な文字起こしのみ
- レイテンシがわずかに低い
- コストがわずかに安い
- **本プロジェクトには不向き**（話者情報がない）

## API呼び出し例

```python
from openai import OpenAI
client = OpenAI()

with open("meeting.wav", "rb") as audio_file:
    transcription = client.audio.transcriptions.create(
        file=audio_file,
        model="gpt-4o-transcribe-diarize",
        response_format="verbose_json",
        timestamp_granularities=["segment"],
        language="ja"  # オプション
    )

# 話者ごとに分類
for segment in transcription.segments:
    print(f"{segment.speaker}: {segment.text}")
```

## 参考リンク

- [OpenAI Audio Guide](https://platform.openai.com/docs/guides/audio)
- [Speech to Text Guide](https://platform.openai.com/docs/guides/speech-to-text)
- [gpt-4o-transcribe-diarize Model Page](https://platform.openai.com/docs/models/gpt-4o-transcribe-diarize)
- [API Reference](https://platform.openai.com/docs/api-reference/audio/createTranscription)
