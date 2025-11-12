#!/usr/bin/env python3
"""
S3へのアップロード補助ツール

使い方:
  python upload_to_s3.py audio_file.wav --bucket my-bucket --prefix raw-audio/
"""

import argparse
import os
import sys
from pathlib import Path
import boto3
from datetime import datetime


def upload_audio_file(
    file_path: str,
    bucket: str,
    prefix: str = "raw-audio/",
    region: str = "ap-northeast-1"
) -> str:
    """
    音声ファイルをS3にアップロード
    
    Args:
        file_path: ローカルの音声ファイルパス
        bucket: S3バケット名
        prefix: S3キーのプレフィックス
        region: AWSリージョン
        
    Returns:
        S3のフルパス（s3://bucket/key）
    """
    # ファイルの存在確認
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)
    
    # ファイル名を取得（タイムスタンプ付き）
    original_name = os.path.basename(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name_without_ext, ext = os.path.splitext(original_name)
    s3_key = f"{prefix}{name_without_ext}_{timestamp}{ext}"
    
    # S3クライアントの作成
    s3_client = boto3.client('s3', region_name=region)
    
    # ファイルサイズを取得
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / 1024 / 1024
    
    print(f"[INFO] Uploading file to S3...")
    print(f"  Local file: {file_path}")
    print(f"  File size: {file_size_mb:.2f} MB")
    print(f"  S3 bucket: {bucket}")
    print(f"  S3 key: {s3_key}")
    
    try:
        # アップロード実行
        s3_client.upload_file(
            file_path,
            bucket,
            s3_key,
            Callback=ProgressPercentage(file_path)
        )
        
        s3_path = f"s3://{bucket}/{s3_key}"
        print(f"\n[SUCCESS] Upload completed!")
        print(f"  S3 path: {s3_path}")
        print(f"\n[INFO] Processing will start automatically...")
        print(f"  Check CloudWatch Logs for progress")
        
        return s3_path
        
    except Exception as e:
        print(f"\n[ERROR] Upload failed: {e}")
        sys.exit(1)


class ProgressPercentage:
    """アップロード進捗を表示するコールバック"""
    
    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._last_percent = 0
    
    def __call__(self, bytes_amount):
        self._seen_so_far += bytes_amount
        percentage = (self._seen_so_far / self._size) * 100
        
        # 10%刻みで進捗を表示
        if int(percentage / 10) > self._last_percent:
            self._last_percent = int(percentage / 10)
            sys.stdout.write(
                f"\r  Progress: {self._seen_so_far / 1024 / 1024:.1f} MB / "
                f"{self._size / 1024 / 1024:.1f} MB ({percentage:.1f}%)"
            )
            sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="音声ファイルをS3にアップロードして議事録作成を開始"
    )
    parser.add_argument(
        'file',
        help='アップロードする音声ファイルのパス'
    )
    parser.add_argument(
        '--bucket',
        required=True,
        help='S3バケット名'
    )
    parser.add_argument(
        '--prefix',
        default='raw-audio/',
        help='S3キーのプレフィックス（デフォルト: raw-audio/）'
    )
    parser.add_argument(
        '--region',
        default='ap-northeast-1',
        help='AWSリージョン（デフォルト: ap-northeast-1）'
    )
    
    args = parser.parse_args()
    
    # アップロード実行
    upload_audio_file(
        args.file,
        args.bucket,
        args.prefix,
        args.region
    )


if __name__ == '__main__':
    main()
