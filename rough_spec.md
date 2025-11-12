MVP実装仕様書（改訂版）：クライアント録音・AWSバッチ処理型システム1. アーキテクチャの再定義：クライアント録音とAWS1.1. プロジェクト目的（変更後）本仕様書は、Microsoft Teams会議に参加しているユーザーのローカルPCで音声を録音し、会議終了後にその音声ファイルをAmazon S3にアップロードすることでバッチ処理を起動するMVP（Minimum Viable Product）の実装仕様を定義する。クラウド基盤はAzureからAWSに変更し、ローカルでの開発・検証を経て、将来的にはAWS LambdaおよびAWS Fargateへのデプロイを目指す。1.2. 核心的な注意点：音声取得方法のトレードオフご要望に基づき、音声取得を「コンポーネント1：音声取得ボット」から「ローカルPCでの録音」に変更します。この変更は、実装の複雑さ（サーバーホスティング、管理者同意 14）を大幅に軽減しますが、議事録の品質（特に話者識別）において重大なトレードオフが発生します。課題（The Two-Stream Problem）: ローカルPCで会議の全音声を取得するには、「自分の声（マイク入力）」と「相手の声（スピーカー出力）」の2つの音源を同時に録音する必要があります 15。技術的実装: Windows環境では、マイク入力（PyAudio 22 や NAudio 23 など）と、スピーカー出力（PyAudioWPatch 24 や NAudio 28 のWASAPIループバック機能 12）を同時に実行し、音声データを合成する必要があります。品質への影響（最重要）: この方法で取得した「相手の声」は、Teamsアプリによって既にミックスされた音声です。つまり、参加者Bと参加者Cが同時に話した場合、音声は1つのトラックに混ざっています。結論: gpt-4o-transcribe-diarize 31 を使用しても、ローカルPCで録音した音声では「自分」と「自分以外の全員（単一話者として）」の2名としてしか識別できない可能性が極めて高くなります。【アーキテクトの警告】「Aさん」「Bさん」「Cさん」のような高精度な話者識別（Diarization）がビジネス要件として必須である場合、クライアントサイドでの録音（方法B）は推奨されません。その場合は、前回のレポートで提案したサーバーサイド・ボット（方法A） 3 の採用を再検討する必要があります。本仕様書は、「自分」と「その他」の分離、あるいは話者識別を諦めることを前提に、ご要望のアーキテクチャを構築します。1.3. システム仕様（AWSアーキテクチャ）本システムは、以下の4コンポーネントで構成されます。ローカル開発の容易さ（コンポーネント3）と、AWSの15分実行時間制限 を回避するスケーラビリティを両立する設計です。クライアント・レコーダー（ローカルアプリ）:役割: ユーザーのPC上で動作し、会議音声（マイク＋スピーカー）を録音し、会議終了後にAmazon S3にアップロードする。技術: Python (PyAudioWPatch 24), C# (NAudio 15) 等。オーケストレーション・トリガー (AWS Lambda):役割: S3へのファイルアップロードを検知 して起動する「軽量な」関数。長時間の処理は実行せず、バッチ処理（Fargate）を起動することのみを目的とする。技術: AWS Lambda (S3 Trigger), Python (Boto3)。バッチ処理エンジン (AWS Fargate):役割: Lambdaから起動される長時間のバッチ処理（OpenAI APIへのリクエスト）を実行するコンテナ。技術: Docker, AWS Fargate (ECS), Python (OpenAI SDK), AWS Secrets Manager。インテリジェンス層 (AWS Lambda):役割: バッチ処理エンジンがS3に出力した「文字起こしJSON」を検知し、LLMによる要約・TODO抽出（短時間処理）を実行する。技術: AWS Lambda (S3 Trigger), Python (OpenAI SDK)。1.4. データフロー（AWS版）録音: ユーザーがローカルPCで [クライアント・レコーダー] を起動。レコーダーはマイク入力とスピーカー出力（WASAPIループバック 12）を同時にキャプチャし、単一の .wav ファイルとして保存します 15。S3アップロード: 会議終了後、ユーザーがボタンを押すか、アプリが自動で .wav ファイルをAmazon S3バケット（例: /raw-audio/）にアップロードします。トリガー1 (Lambda): S3へのアップロード をトリガーに、[オーケストレーション・トリガー]（Lambda関数）が起動します。Fargateタスク起動: Lambda関数は、長時間処理（15分以上） に対応するため、boto3 を使用して [バッチ処理エンジン]（Fargateタスク）を非同期で起動します。この際、処理対象のS3ファイルパスをFargateタスクの環境変数として渡します。STT API実行 (Fargate): Fargateコンテナが起動。S3から .wav ファイルをダウンロードし、AWS Secrets Manager からOpenAI APIキーを取得します。Fargateタスクは、OpenAIの /v1/audio/transcriptions API 31 にファイルを送信します（model='gpt-4o-transcribe-diarize' 31, response_format='diarized_json' 31）。トランスクリプト保存: OpenAIから diarized_json を受け取り、別のS3コンテナ（例: /transcripts/）に meeting_id.json として保存します。Fargateタスクはここで終了します。トリガー2 (Lambda): /transcripts/ へのJSONファイル保存をトリガーに、[インテリジェンス層]（Lambda関数）が起動します。LLM実行: このLambdaは短時間で完了します。S3から diarized_json を読み込み、Secrets ManagerからAPIキーを取得し、GPT-4o（Chat API）に要約・TODO抽出を依頼します。成果物通知: 生成された成果物を、Amazon SNS経由でメール送信、またはAmazon EventBridge経由で外部Webhook（Teamsチャネル等）に通知します。2. 実現方式の詳細 (AWS & ローカル開発)2.1. コンポーネント1：クライアント・レコーダー (Python実装例)これはユーザーのWindows PC上で動作するローカルアプリケーションです。必須ライブラリ: PyAudioWPatch 24 (スピーカー録音用), PyAudio (マイク録音用), wave (ファイル保存用), boto3 (S3アップロード用)。中核ロジック:デバイスの特定: PyAudioWPatch を使い、デフォルトのスピーカー（ループバックデバイス）を特定します 24。同時録音（2ストリーム）: 2つのスレッド（Thread）を起動します 20。スレッド1: PyAudioWPatch を使い、スピーカー（ループバック）からの音声を録音し、キュー（Queue）にデータを入れます 26。スレッド2: PyAudio を使い、デフォルトのマイクからの音声を録音し、別のキューに入れます 17。音声の合成と保存: メインスレッドは両方のキューから音声データを取得し、wave モジュールを使って .wav ファイルに書き込みます。注意： 2つのストリームを1つのモノラルファイルにミックスダウン（単純加算） 19 するか、2チャンネル（ステレオ）ファイルとして保存（左:マイク, 右:スピーカー）するかを決定する必要があります。後者（ステレオ）の方が、話者識別の品質がわずかに向上するため推奨されます。S3アップロード: 録音終了後、boto3 の s3_client.upload_file() を使用して、S3バケットにファイルをアップロードします。2.2. コンポーネント2 & 3：S3 -> Lambda -> Fargateローカル開発を優先するため、まず**[コンポーネント3] (Fargate)** となるDockerコンテナを作成します。2.2.1. コンポーネント3：バッチ処理エンジン (Docker / Fargate)Dockerfile (Pythonベース)DockerfileFROM python:3.10-slim
RUN pip install openai boto3
COPY transcribe.py.
ENTRYPOINT ["python", "transcribe.py"]
transcribe.py (Fargateタスクの本体)Pythonimport os
import boto3
import json
from openai import OpenAI

# 環境変数からS3の情報を取得 (Lambdaから渡される)
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_KEY_INPUT = os.environ.get('S3_KEY_INPUT') # 例: "raw-audio/meeting_id.wav"
S3_KEY_OUTPUT = os.environ.get('S3_KEY_OUTPUT') # 例: "transcripts/meeting_id.json"
SECRET_NAME = os.environ.get('OPENAI_API_KEY_SECRET_NAME') # 例: "MyOpenAIKey"

# 1. APIキーをAWS Secrets Managerから取得
def get_openai_key():
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager')
    try:
        get_secret_value_response = client.get_secret_value(SecretId=SECRET_NAME)
        secret = get_secret_value_response
        return json.loads(secret)
    except Exception as e:
        print(f"Error retrieving secret: {e}")
        raise e

# 2. ローカル開発（テスト）用のコード
def process_local_file(local_path, api_key):
    client = OpenAI(api_key=api_key)
    print(f"Processing local file: {local_path}...")

    with open(local_path, "rb") as audio_file:
        transcription_response = client.audio.transcriptions.create(
            file=audio_file,
            model="gpt-4o-transcribe-diarize",
            response_format="diarized_json"
        )
    # 結果をローカルに出力
    print(transcription_response)
    with open("local_output.json", "w") as f:
        f.write(transcription_response)

# 3. AWS Fargate上で実行されるメインロジック
def process_s3_file(api_key):
    s3_client = boto3.client('s3')
    local_filename = '/tmp/audio.wav'

    # S3からファイルをダウンロード
    print(f"Downloading {S3_KEY_INPUT} from {S3_BUCKET}...")
    s3_client.download_file(S3_BUCKET, S3_KEY_INPUT, local_filename)

    # OpenAI API呼び出し
    client = OpenAI(api_key=api_key)
    print("Sending to OpenAI API...")
    with open(local_filename, "rb") as audio_file:
        transcription_response = client.audio.transcriptions.create(
            file=audio_file,
            model="gpt-4o-transcribe-diarize",
            response_format="diarized_json"
        )

    # S3に結果をアップロード
    print(f"Uploading transcript to {S3_KEY_OUTPUT}...")
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=S3_KEY_OUTPUT,
        Body=transcription_response
    )
    print("Processing complete.")

if __name__ == "__main__":
    # --- ローカル開発時のテスト ---
    # 以下のコメントを解除し、環境変数を設定してローカル実行
    # os.environ = "sk-..." # または環境変数で設定
    # process_local_file("path/to/my_test_audio.wav", os.environ.get('OPENAI_API_KEY'))

    # --- AWS Fargate実行時のロジック ---
    if S3_BUCKET:
        api_key = get_openai_key()
        process_s3_file(api_key)
    else:
        print("Running in local mode (simulation). Set S3_BUCKET to run in Fargate mode.")
2.2.2. コンポーネント2：オーケストレーション・トリガー (Lambda)このLambda関数は、S3イベントをトリガーに設定します。lambda_function.pyPythonimport boto3
import os
import json

ecs_client = boto3.client('ecs')

def lambda_handler(event, context):
    # 1. S3イベントからバケット名とキーを取得
    s3_record = event['s3']
    bucket_name = s3_record['bucket']['name']
    object_key = s3_record['object']['key']

    # 出力先のキーを決定
    output_key = "transcripts/" + os.path.basename(object_key) + ".json"

    # 2. Fargateタスクの起動パラメータを設定
    task_params = {
        'cluster': os.environ,
        'taskDefinition': os.environ,
        'launchType': 'FARGATE',
        'networkConfiguration': {
            'awsvpcConfiguration': {
                'subnets': json.loads(os.environ), # '["subnet-123", "subnet-456"]'
                'assignPublicIp': 'ENABLED' # OpenAI APIにアクセスするため
            }
        },
        'overrides': {
            'containerOverrides':, # Dockerコンテナ名
                'environment':}
                ]
            }]
        }
    }

    # 3. Fargateタスクを実行
    try:
        response = ecs_client.run_task(**task_params)
        print(f"Started Fargate task: {response['tasks']['taskArn']}")
        return {'statusCode': 200}
    except Exception as e:
        print(f"Error starting Fargate task: {e}")
        raise e
2.3. コンポーネント4：インテリジェンス層 (Lambda)このLambda関数は、/transcripts/ バケットへのS3イベントをトリガーにします。これは短時間（数秒）で終わるため、Fargateは不要です。実装は前回のレポート（2.3）とほぼ同様ですが、APIキー取得部分が boto3 (Secrets Manager) に変わります。3. 実装にあたっての要点や注意点（AWS版）最大の懸念事項（再掲）: クライアントサイドでの録音（方法B）は、話者識別の品質を著しく低下させます。「自分」と「その他全員」の分離しか期待できません。Windows依存の録音: WASAPIループバック 12 はWindowsの機能です。PyAudioWPatch 24 もWindows専用です。もしMacユーザーも対象とする場合、Mac用の別途の音声キャプチャ（例：BlackHoleやScreenCaptureKit）の実装が必要となり、プロジェクトの複雑性が増大します。プロセス固有のキャプチャ: 単純なWASAPIループバックは、PCで再生される全ての音（YouTube、OSの通知音など）を録音してしまいます 36。これを避けるには、Windows 10 (Build 20348+) 以降で利用可能な ActivateAudioInterfaceAsync API 38 を使い、「Teams.exe」プロセスの音声のみをキャプチャする高度な実装が必要です。Lambdaの15分制限の回避（必須）: 1時間の会議の音声ファイル（~100MB以上）のダウンロード、OpenAIへのアップロード、およびAPI処理（数分〜数十分）は、AWS Lambdaの実行時間15分の壁 とペイロード制限（6MB） を確実に超えます。したがって、S3 -> Lambda -> Fargate というアーキテクチャは、このプロジェクトにおいて必須の設計です。セキュリティ（APIキー）: OpenAIのAPIキーは、ローカルアプリにも、Lambda/Fargateコンテナにも絶対にハードコードしないでください。AWS Secrets Manager を使用し、LambdaおよびFargateタスクのIAMロールに secretsmanager:GetSecretValue の権限を付与して、実行時に動的に取得してください。ローカル開発: transcribe.py をローカルで実行することで、Fargateへのデプロイ前にOpenAI APIの呼び出しロジックを迅速にテストできます。これがこのアーキテクチャの利点です。