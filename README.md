# MediGate AI MVP

症状入力から適切な診療科の推奨と、田町・上野・柏の各駅周辺（または現在地）の医療機関を案内するアプリケーションです。

## 機能フロー

1. **症状入力** - ユーザーが症状を入力
2. **追加質問** - AI が症状を詳しく把握するための質問を生成
3. **推奨科表示** - 症状に基づいて受診を推奨する診療科を表示（診断なし）
4. **医療機関表示** - 田町・上野・柏周辺（または現在地）の病院・クリニックを表示（検索半径・件数は選択可能）
5. **専門医情報（ウェブ検索）** - 各医療機関について、専門医・認定医などの情報をウェブ検索で取得し、**ソース（URL）付き**で表示（任意・ボタンで実行）
6. **PQRST メモ** - 医師向けの症状メモ（PQRST 形式）を生成

## 必要な API・サービス

- **Vertex AI (Gemini)** - 追加質問、推奨科、PQRST メモの生成
- **Vertex AI（Google Search グラウンディング）** - 専門医情報のウェブ検索（GCP コンソールで「検索候補」を有効化する必要がある場合があります）
- **クリニックデータ** - `output/clinics_merged.csv`（検索起点は現在地または田町・上野・柏駅）

## セットアップ

### 1. 環境変数

`.env.example` を `.env` にコピーし、値を設定：

```bash
cp .env.example .env
```

- `GOOGLE_CLOUD_PROJECT`: Vertex AI を使用する GCP プロジェクト ID
- （任意）`VERTEX_LOCATION`: Vertex AI のリージョン（未設定時は `us-central1`）

### 2. GCP 認証（Vertex AI 用）

```bash
gcloud auth application-default login
```

### 3. ローカル実行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Cloud Run へのデプロイ

**詳細な手順は [docs/DEPLOY.md](docs/DEPLOY.md) を参照してください。** ここでは最小限のコマンドのみ記載します。

プロジェクトルートで以下を実行（`output/clinics_merged.csv` が存在する状態でデプロイしてください）。

```bash
gcloud run deploy medigate-ai \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated
```

**環境変数**は Cloud Run の「リビジョン」→ 該当サービス → 「変数とシークレット」で設定するか、デプロイ時に指定します：

```bash
gcloud run deploy medigate-ai \
  --source . \
  --region asia-northeast1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=your-project-id,VERTEX_LOCATION=asia-northeast1"
```

- `GOOGLE_CLOUD_PROJECT`: 必須。Vertex AI 用の GCP プロジェクト ID
- `VERTEX_LOCATION`: 任意。未設定時は `asia-northeast1`

**認証**: Cloud Run のサービスアカウントに Vertex AI の利用権限が必要です。同一プロジェクトであれば「Vertex AI ユーザー」ロールを付与してください。

**表示用 URL**: デプロイ成功時にターミナルに表示される **Service URL**（`https://...run.app`）がアプリのアドレスです。見逃した場合は `gcloud run services describe medigate-ai --region=asia-northeast1 --format="value(status.url)"` で取得できます。詳細は [docs/DEPLOY.md の「10. デプロイ後の URL」](docs/DEPLOY.md#10-デプロイ後の-url-の確認) を参照。

**ビルドが失敗する場合**: [docs/DEPLOY.md](docs/DEPLOY.md) の「8.7 2段階デプロイ」を試してください。**GitHub へのアップロード**手順は [docs/DEPLOY.md の「11. GitHub へのアップロード」](docs/DEPLOY.md#11-github-へのアップロード) を参照。

## 注意事項

- 本システムは診断を行いません。正確な診断は必ず医師の診察を受けてください
- 混雑・待ち時間は表示しません
