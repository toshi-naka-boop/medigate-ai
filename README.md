# MediGate AI MVP

症状入力から適切な診療科の推奨と柏駅周辺の医療機関を案内するアプリケーションです。

## 機能フロー

1. **症状入力** - ユーザーが症状を入力
2. **追加質問** - AI が症状を詳しく把握するための質問を生成
3. **推奨科表示** - 症状に基づいて受診を推奨する診療科を表示（診断なし）
4. **医療機関表示** - 柏駅周辺の病院・クリニック 3〜10 件を表示
5. **PQRST メモ** - 医師向けの症状メモ（PQRST 形式）を生成

## 必要な API・サービス

- **Google Places API** - 柏駅の位置取得、周辺の医療機関検索
- **Vertex AI (Gemini)** - 追加質問、推奨科、PQRST メモの生成

## セットアップ

### 1. 環境変数

`.env.example` を `.env` にコピーし、値を設定：

```bash
cp .env.example .env
```

- `GOOGLE_PLACES_API_KEY`: Google Cloud Console で Places API を有効化し API キーを発行
- `GOOGLE_CLOUD_PROJECT`: Vertex AI を使用する GCP プロジェクト ID

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

```bash
gcloud run deploy medicate-ai \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated
```

環境変数は Cloud Run のコンソールまたは `--set-env-vars` で設定：

```bash
gcloud run deploy medicate-ai \
  --source . \
  --region asia-northeast1 \
  --set-env-vars "GOOGLE_PLACES_API_KEY=xxx,GOOGLE_CLOUD_PROJECT=your-project"
```

## 注意事項

- 本システムは診断を行いません。正確な診断は必ず医師の診察を受けてください
- 混雑・待ち時間は表示しません
