"""
インテリジェンス層 Lambda関数

文字起こしJSONを解析し、GPT-4oで要約・TODO抽出を実行
"""

import os
import json
import boto3
from datetime import datetime
from urllib.parse import unquote_plus
from openai import OpenAI

s3_client = boto3.client('s3')
sns_client = boto3.client('sns')

# 環境変数
SECRET_NAME = os.environ.get('OPENAI_API_KEY_SECRET_NAME')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')  # オプション: 通知用
OUTPUT_FORMAT = os.environ.get('OUTPUT_FORMAT', 'json')  # json, markdown, both


def get_openai_key_from_secrets_manager() -> str:
    """AWS Secrets ManagerからOpenAI APIキーを取得"""
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager')
    
    try:
        get_secret_value_response = client.get_secret_value(SecretId=SECRET_NAME)
        secret = get_secret_value_response['SecretString']
        
        try:
            secret_dict = json.loads(secret)
            return secret_dict.get('OPENAI_API_KEY') or secret_dict.get('api_key')
        except json.JSONDecodeError:
            return secret
            
    except Exception as e:
        print(f"[ERROR] Failed to retrieve secret: {e}")
        raise e


def create_summary_prompt(transcript_data: dict) -> str:
    """
    文字起こしデータから要約生成用のプロンプトを作成
    
    Args:
        transcript_data: OpenAI Speech-to-Text APIの出力JSON
        
    Returns:
        GPT-4o用のプロンプト
    """
    # 文字起こしテキストを取得
    text = transcript_data.get('text', '')
    
    prompt = f"""以下は会議の文字起こしです。この内容を分析して、以下の形式でJSONを生成してください。

【文字起こしテキスト】
{text}

【出力形式】
{{
  "summary": "会議の要約（200-300文字程度）",
  "key_points": [
    "重要なポイント1",
    "重要なポイント2",
    "重要なポイント3"
  ],
  "decisions": [
    "決定事項1",
    "決定事項2"
  ],
  "action_items": [
    {{
      "task": "タスクの内容",
      "assignee": "担当者（不明な場合は null）",
      "deadline": "期限（不明な場合は null）"
    }}
  ],
  "next_steps": [
    "次のステップ1",
    "次のステップ2"
  ]
}}

注意事項:
- 日本語で出力してください
- JSONフォーマットを厳密に守ってください
- 文字起こしに含まれない情報は推測しないでください
- action_itemsが見つからない場合は空の配列を返してください
"""
    
    return prompt


def generate_summary(transcript_data, api_key):
    """
    OpenAI GPT-4oで文字起こしテキストを要約
    
    Args:
        transcript_data: OpenAI Speech-to-Text APIの出力JSON
        api_key: OpenAI APIキー
    
    Returns:
        dict: 要約データ（summary, key_topics, action_items, speakers）
    """
    client = OpenAI(api_key=api_key)
    
    prompt = create_summary_prompt(transcript_data)
    
    print(f"[INFO] Generating summary with GPT-4o...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "あなたは会議の議事録を作成する専門家です。文字起こしテキストから、要約、重要なポイント、決定事項、アクションアイテムを抽出してください。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        # レスポンスからJSONを抽出
        summary_text = response.choices[0].message.content
        summary_data = json.loads(summary_text)
        
        print(f"[SUCCESS] Summary generated")
        return summary_data
        
    except Exception as e:
        print(f"[ERROR] Failed to generate summary: {e}")
        raise e


def convert_to_markdown(summary_data: dict) -> str:
    """
    JSON形式の要約をMarkdown形式に変換
    
    Args:
        summary_data: 要約データ（JSON）
        
    Returns:
        Markdown形式のテキスト
    """
    md_lines = []
    
    # タイトル
    md_lines.append("# 議事録")
    md_lines.append("")
    
    # メタデータ
    metadata = summary_data.get('metadata', {})
    if metadata:
        md_lines.append("## メタデータ")
        md_lines.append(f"- **生成日時**: {metadata.get('generated_at', 'N/A')}")
        md_lines.append(f"- **元ファイル**: `{metadata.get('transcript_s3_key', 'N/A')}`")
        if metadata.get('transcript_duration'):
            md_lines.append(f"- **会議時間**: {metadata.get('transcript_duration')}秒")
        md_lines.append("")
    
    # 要約
    md_lines.append("## 要約")
    md_lines.append(summary_data.get('summary', ''))
    md_lines.append("")
    
    # 重要なポイント
    key_points = summary_data.get('key_points', [])
    if key_points:
        md_lines.append("## 重要なポイント")
        for point in key_points:
            md_lines.append(f"- {point}")
        md_lines.append("")
    
    # 決定事項
    decisions = summary_data.get('decisions', [])
    if decisions:
        md_lines.append("## 決定事項")
        for decision in decisions:
            md_lines.append(f"- {decision}")
        md_lines.append("")
    
    # アクションアイテム
    action_items = summary_data.get('action_items', [])
    if action_items:
        md_lines.append("## アクションアイテム")
        for item in action_items:
            task = item.get('task', '')
            assignee = item.get('assignee') or '未割当'
            deadline = item.get('deadline') or '期限未定'
            md_lines.append(f"- [ ] **{task}**")
            md_lines.append(f"  - 担当: {assignee}")
            md_lines.append(f"  - 期限: {deadline}")
        md_lines.append("")
    
    # 次のステップ
    next_steps = summary_data.get('next_steps', [])
    if next_steps:
        md_lines.append("## 次のステップ")
        for step in next_steps:
            md_lines.append(f"- {step}")
        md_lines.append("")
    
    return '\n'.join(md_lines)


def send_notification(bucket: str, summary_key: str, summary_data: dict):
    """
    SNS経由で通知を送信（オプション）
    
    Args:
        bucket: S3バケット名
        summary_key: 要約JSONのS3キー
        summary_data: 要約データ
    """
    if not SNS_TOPIC_ARN:
        print("[INFO] SNS_TOPIC_ARN not configured, skipping notification")
        return
    
    try:
        message = f"""議事録の生成が完了しました

【要約】
{summary_data.get('summary', '')}

【重要なポイント】
{chr(10).join(f"- {point}" for point in summary_data.get('key_points', []))}

【アクションアイテム】
{chr(10).join(f"- {item.get('task', '')}" for item in summary_data.get('action_items', []))}

【詳細】
s3://{bucket}/{summary_key}
"""
        
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="議事録生成完了",
            Message=message
        )
        
        print(f"[SUCCESS] Notification sent to SNS")
        
    except Exception as e:
        print(f"[WARNING] Failed to send notification: {e}")


def lambda_handler(event, context):
    """
    S3の文字起こしJSONをトリガーに要約・TODO抽出を実行
    
    Args:
        event: S3 PUT イベント
        context: Lambda コンテキスト
    """
    print(f"[INFO] Received event: {json.dumps(event)}")
    
    try:
        # APIキーを取得
        api_key = get_openai_key_from_secrets_manager()
        
        # S3イベントからバケット名とキーを取得
        for record in event.get('Records', []):
            s3_info = record.get('s3', {})
            bucket_name = s3_info.get('bucket', {}).get('name')
            transcript_key = unquote_plus(s3_info.get('object', {}).get('key', ''))
            
            print(f"[INFO] Processing transcript:")
            print(f"  Bucket: {bucket_name}")
            print(f"  Key: {transcript_key}")
            
            # S3から文字起こしJSONを取得
            response = s3_client.get_object(Bucket=bucket_name, Key=transcript_key)
            file_content = response['Body'].read().decode('utf-8')
            
            # JSONまたはプレーンテキストとして処理
            try:
                # まずJSONとしてパース
                transcript_data = json.loads(file_content)
                text = transcript_data.get('text', '')
                print(f"[INFO] Loaded as JSON, text length: {len(text)} characters")
            except json.JSONDecodeError:
                # JSONでない場合はプレーンテキストとして扱う
                text = file_content
                transcript_data = {'text': text}
                print(f"[INFO] Loaded as plain text, length: {len(text)} characters")
            
            # 要約・TODO抽出を実行
            summary_data = generate_summary(transcript_data, api_key)
            
            # メタデータを追加
            summary_data['metadata'] = {
                'transcript_s3_key': transcript_key,
                'generated_at': datetime.utcnow().isoformat(),
                'transcript_length': len(transcript_data.get('text', '')),
                'transcript_duration': transcript_data.get('duration')
            }
            
            # 出力先のキーを決定（ディレクトリ構造を保持）
            # 例: transcripts/nozaki/2025-11-12/meeting.txt -> summaries/nozaki/2025-11-12/meeting.json
            # transcripts/ プレフィックスを summaries/ に置き換え、ディレクトリ構造はそのまま保持
            if transcript_key.startswith('transcripts/'):
                relative_path = transcript_key[len('transcripts/'):]
                base_name = os.path.splitext(relative_path)[0]
            else:
                # transcripts/ で始まらない場合のフォールバック
                base_name = os.path.splitext(os.path.basename(transcript_key))[0]
            
            # 出力形式に応じてファイルを保存
            output_format = OUTPUT_FORMAT.lower()
            
            if output_format in ['json', 'both']:
                # JSON形式で保存
                summary_key = f"summaries/{base_name}.json"
                print(f"[INFO] Saving summary (JSON) to S3: {summary_key}")
                
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=summary_key,
                    Body=json.dumps(summary_data, ensure_ascii=False, indent=2).encode('utf-8'),
                    ContentType='application/json'
                )
                print(f"[SUCCESS] JSON summary saved to: s3://{bucket_name}/{summary_key}")
            
            if output_format in ['markdown', 'both']:
                # Markdown形式で保存
                markdown_key = f"summaries/{base_name}.md"
                markdown_content = convert_to_markdown(summary_data)
                print(f"[INFO] Saving summary (Markdown) to S3: {markdown_key}")
                
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=markdown_key,
                    Body=markdown_content.encode('utf-8'),
                    ContentType='text/markdown'
                )
                print(f"[SUCCESS] Markdown summary saved to: s3://{bucket_name}/{markdown_key}")
            
            # 最後に保存したキーを記録（通知用）
            final_summary_key = summary_key if output_format in ['json', 'both'] else markdown_key
            
            # 通知を送信（オプション）
            send_notification(bucket_name, final_summary_key, summary_data)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Summary generated successfully',
                'summary_key': final_summary_key if 'final_summary_key' in locals() else None,
                'output_format': OUTPUT_FORMAT
            })
        }
        
    except Exception as e:
        print(f"[ERROR] Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error generating summary',
                'error': str(e)
            })
        }
