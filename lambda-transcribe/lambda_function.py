"""
文字起こし Lambda関数

S3に音声ファイルがアップロードされたことを検知し、
OpenAI Speech-to-Text API（話者識別機能付き）で文字起こしを実行してS3に保存
"""

import os
import json
from urllib.parse import unquote_plus
import boto3
from openai import OpenAI

s3_client = boto3.client('s3')

# 環境変数
SECRET_NAME = os.environ.get('OPENAI_API_KEY_SECRET_NAME')  # Secrets Manager用


def get_openai_key_from_secrets_manager() -> str:
    """AWS Secrets ManagerからOpenAI APIキーを取得"""
    secrets_client = boto3.client('secretsmanager')
    
    try:
        response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
        secret = response['SecretString']
        
        try:
            secret_dict = json.loads(secret)
            return secret_dict.get('OPENAI_API_KEY') or secret_dict.get('api_key')
        except json.JSONDecodeError:
            return secret
            
    except Exception as e:
        print(f"[ERROR] Failed to retrieve secret: {e}")
        raise e


def transcribe_audio_from_s3(bucket, key, api_key):
    """
    S3から音声ファイルを取得してOpenAI Speech-to-Text APIで文字起こし
    
    Args:
        bucket: S3バケット名
        key: S3オブジェクトキー
        api_key: OpenAI APIキー
        
    Returns:
        文字起こし結果（verbose_json形式）
    """
    client = OpenAI(api_key=api_key)
    
    # S3から音声ファイルをダウンロード（拡張子を保持）
    file_extension = os.path.splitext(key)[1]
    local_file = f'/tmp/audio_file{file_extension}'
    
    print(f"[INFO] Downloading from S3...")
    print(f"  Bucket: {bucket}")
    print(f"  Key: {key}")
    
    s3_client.download_file(bucket, key, local_file)
    
    file_size_mb = os.path.getsize(local_file) / 1024 / 1024
    print(f"[INFO] File downloaded: {file_size_mb:.2f} MB")
    
    # OpenAI Speech-to-Text API呼び出し
    print(f"[INFO] Calling OpenAI Speech-to-Text API...")
    
    try:
        with open(local_file, "rb") as audio_file:
            # OpenAI 最新モデルで文字起こし（話者識別付き）
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="gpt-4o-transcribe-diarize",  # 最新モデル（話者識別対応）
                response_format="diarized_json",  # 話者識別JSON形式（segmentsに話者情報を含む）
                chunking_strategy="auto",  # diarizationモデルでは必須
                language="ja"  # 日本語を指定（自動検出も可能: 省略可）
            )
        
        print(f"[SUCCESS] Transcription completed")
        print(f"[INFO] Transcript length: {len(transcription.text)} characters")
        
        # レスポンスの構造をログ出力（デバッグ用）
        response_dict = transcription.model_dump()
        print(f"[DEBUG] Response keys: {list(response_dict.keys())}")
        
        # 話者識別情報の確認
        if 'segments' in response_dict and response_dict['segments']:
            print(f"[INFO] Number of segments: {len(response_dict['segments'])}")
            # 最初のセグメントをサンプル出力
            first_segment = response_dict['segments'][0]
            print(f"[DEBUG] First segment: speaker={first_segment.get('speaker')}, text={first_segment.get('text')[:50] if first_segment.get('text') else 'N/A'}...")
        else:
            print(f"[WARNING] No segments found in response")
        
        # 一時ファイルを削除
        if os.path.exists(local_file):
            os.remove(local_file)
        
        return transcription.model_dump()
        
    except Exception as e:
        print(f"[ERROR] Transcription failed: {e}")
        # 一時ファイルを削除
        if os.path.exists(local_file):
            os.remove(local_file)
        raise e


def lambda_handler(event, context):
    """
    S3イベントをトリガーに文字起こしを実行
    
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
            input_key = unquote_plus(s3_info.get('object', {}).get('key', ''))
            
            print(f"[INFO] Processing audio file:")
            print(f"  Bucket: {bucket_name}")
            print(f"  Key: {input_key}")
            
            # 文字起こし実行
            transcript_data = transcribe_audio_from_s3(bucket_name, input_key, api_key)
            
            # 出力先のキーを決定（ディレクトリ構造を保持）
            # 例: raw-audio/nozaki/2025-11-12/meeting.wav -> transcripts/nozaki/2025-11-12/meeting.json
            # raw-audio/ プレフィックスを transcripts/ に置き換え、ディレクトリ構造はそのまま保持
            if input_key.startswith('raw-audio/'):
                relative_path = input_key[len('raw-audio/'):]
                base_name = os.path.splitext(relative_path)[0]
                output_key = f"transcripts/{base_name}.json"
            else:
                # raw-audio/ で始まらない場合のフォールバック
                file_name = os.path.basename(input_key)
                base_name = os.path.splitext(file_name)[0]
                output_key = f"transcripts/{base_name}.json"
            
            # S3に結果を保存
            print(f"[INFO] Saving transcript to S3: {output_key}")
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=output_key,
                Body=json.dumps(transcript_data, ensure_ascii=False, indent=2).encode('utf-8'),
                ContentType='application/json'
            )
            
            print(f"[SUCCESS] Transcript saved to: s3://{bucket_name}/{output_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Transcription completed successfully',
                'output_key': output_key if 'output_key' in locals() else None
            })
        }
        
    except Exception as e:
        print(f"[ERROR] Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error during transcription',
                'error': str(e)
            })
        }

