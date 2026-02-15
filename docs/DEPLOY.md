# Cloud Run デプロイ手順（詳細）

MediGate AI を Google Cloud Run にデプロイする手順を、初回から順に説明します。

---

## 1. 前提条件

- **Google Cloud アカウント**（[console.cloud.google.com](https://console.cloud.google.com) で作成）
- **Google Cloud CLI（gcloud）** がインストール済みであること  
  - 未インストール: [Google Cloud CLI のインストール](https://cloud.google.com/sdk/docs/install)
- デプロイする **GCP プロジェクト ID** を決めておく（既存プロジェクトでも新規作成でも可）

---

## 2. gcloud のログインとプロジェクト設定

### 2.1 ログイン

```bash
gcloud auth login
```

ブラウザが開くので、デプロイに使う Google アカウントでログインします。

### 2.2 デフォルトプロジェクトを設定

```bash
# プロジェクト一覧で ID を確認
gcloud projects list

# 使用するプロジェクトをデフォルトに設定
gcloud config set project YOUR_PROJECT_ID
```

`YOUR_PROJECT_ID` を実際のプロジェクト ID に置き換えてください。

### 2.3 アプリケーションのデフォルト認証（ローカルで Vertex を試す場合）

Cloud Run デプロイ時には必須ではありませんが、ローカルで Vertex AI を試す場合は以下を実行します。

```bash
gcloud auth application-default login
```

---

## 3. 必要な API の有効化

Cloud Run と Vertex AI の API を有効にします。

```bash
# Cloud Run API
gcloud services enable run.googleapis.com

# Vertex AI API
gcloud services enable aiplatform.googleapis.com

# ソースからビルドする場合は Cloud Build も必要
gcloud services enable cloudbuild.googleapis.com
```

**コンソールから行う場合**

1. [Google Cloud Console](https://console.cloud.google.com) を開く  
2. 画面上部のプロジェクトを選択  
3. 「API とサービス」→「ライブラリ」  
4. 上記の API 名で検索し、それぞれ「有効にする」をクリック  

---

## 4. デプロイ前の準備（ローカル）

### 4.1 クリニック CSV の配置

アプリは起動時に `output/clinics_merged.csv` を読み込みます。**このファイルがプロジェクト内にある状態でデプロイ**してください。

```text
medigate-ai/
├── app.py
├── output/
│   └── clinics_merged.csv   ← 必須（ここに配置）
├── services/
├── Dockerfile
└── ...
```

CSV が無い場合は、用意した CSV を `output/clinics_merged.csv` として保存するか、既存のマージスクリプトで生成してください。

### 4.2 環境変数について

- 本番では **`.env` は使わず**、Cloud Run の「環境変数」で設定します。  
- デプロイ時に `--set-env-vars` で渡すか、コンソールの「変数とシークレット」で後から設定します。

---

## 5. デプロイの実行

### 5.1 プロジェクトルートに移動

```bash
cd /path/to/medigate-ai
```

### 5.2 最小限のデプロイ（環境変数は後で設定する場合）

```bash
gcloud run deploy medigate-ai \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated
```

- `--source .` … カレントディレクトリをソースとして Cloud Build でビルドし、そのイメージを Cloud Run にデプロイします。  
- `--region asia-northeast1` … 東京リージョンでデプロイします。  
- `--allow-unauthenticated` … 認証なしで URL にアクセスできるようにします。

初回は「API を有効にしますか？」と聞かれたら `y` で有効化してください。

### 5.3 環境変数付きでデプロイ（推奨）

Vertex AI を使うため、**デプロイ時に環境変数を渡す**ことを推奨します。

```bash
gcloud run deploy medigate-ai \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,VERTEX_LOCATION=asia-northeast1"
```

- `YOUR_PROJECT_ID` … 実際の GCP プロジェクト ID に置き換えてください。  
- `VERTEX_LOCATION` … Vertex AI のリージョン（東京なら `asia-northeast1` のままで問題ありません）。

### 5.4 メモリ・CPU を変えたい場合

Streamlit と CSV 読み込みを考慮し、メモリを多めにしたい例です。

```bash
gcloud run deploy medigate-ai \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,VERTEX_LOCATION=asia-northeast1"
```

---

## 6. デプロイ後の操作

### 6.1 URL の確認

デプロイが終わると、ターミナルに **サービスの URL** が表示されます。

```text
Service [medigate-ai] revision [medigate-ai-xxxxx] has been deployed and is serving 100 percent of traffic.
Service URL: https://medigate-ai-xxxxxxxx-an.a.run.app
```

この URL をブラウザで開いて動作を確認します。

### 6.2 環境変数を後から追加・変更する場合

1. [Cloud Run コンソール](https://console.cloud.google.com/run) を開く  
2. サービス一覧から **medigate-ai** をクリック  
3. 上部の「編集」→「変数とシークレット」  
4. 「変数を追加」で以下を設定  
   - 名前: `GOOGLE_CLOUD_PROJECT`、値: プロジェクト ID  
   - 名前: `VERTEX_LOCATION`、値: `asia-northeast1`（任意）  
5. 「デプロイ」で新しいリビジョンがデプロイされます  

---

## 7. 権限（サービスアカウント）

Cloud Run のサービスは、デフォルトの「Compute Engine のデフォルト サービス アカウント」で動きます。同一プロジェクトで Vertex AI を使う場合は、多くの場合そのままで動作します。

**403 や権限エラーが出る場合**は、そのサービスアカウントに Vertex AI の権限を付与します。

1. [IAM と管理](https://console.cloud.google.com/iam-admin/iam) を開く  
2. メンバー一覧から  
   `YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com`  
   のような「Compute Engine のデフォルト サービス アカウント」を探す  
3. 編集（鉛筆アイコン）→「別のロールを追加」  
4. 「Vertex AI ユーザー」を追加して保存  

CLI で行う例（プロジェクト番号とサービスアカウントは環境に合わせて置き換えてください）:

```bash
# プロジェクト番号を確認
gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)'

# デフォルトの Cloud Run 用サービスアカウントに Vertex AI ユーザーを付与
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

---

## 8. トラブルシューティング

### 8.2 「403 Permission aiplatform.endpoints.predict denied」が出る場合

Cloud Run 上で Vertex AI（Gemini）を呼び出すと、上記のエラーになる場合は、**Cloud Run が使っているサービスアカウント**に Vertex AI の利用権限がありません。次のコマンドで「Vertex AI ユーザー」ロールを付与してください。

PowerShell（`gcloud.cmd` 使用、プロジェクト ID が `medigate-ai` の場合）:

```powershell
$PROJECT_ID = "medigate-ai"
$PN = (gcloud.cmd projects describe $PROJECT_ID --format="value(projectNumber)")
gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${PN}-compute@developer.gserviceaccount.com" --role="roles/aiplatform.user"
```

付与後、**数分待ってから** Cloud Run のアプリで再度 Vertex AI の機能（追加質問・推奨科・専門医検索など）を試してください。変更が反映されるまで少しかかることがあります。

（Cloud Run で別のサービスアカウントを指定している場合は、そのサービスアカウントのメールアドレスに上記の `--member` を置き換えて付与してください。）

### 8.3 「403: storage.objects.get access ... denied」が出る場合

`--source .` でアップロードしたソースを Cloud Build が GCS から読む際、**デフォルトのサービスアカウントにストレージ権限がない**とこのエラーになります。次の 2 アカウントに「Storage オブジェクトの閲覧者」を付与してください。

**Linux / macOS / Git Bash:**
```bash
PROJECT_ID=medigate-ai   # 実際のプロジェクト ID に変更
PN=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PN}-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PN}@cloudbuild.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

**Windows の PowerShell** で「スクリプトの実行が無効」と出る場合は、`gcloud` の代わりに **`gcloud.cmd`** を使ってください（`.ps1` が実行されずに済みます）:
```powershell
$PROJECT_ID = "medigate-ai"
$PN = (gcloud.cmd projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${PN}-compute@developer.gserviceaccount.com" --role="roles/storage.objectViewer"

gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${PN}@cloudbuild.gserviceaccount.com" --role="roles/storage.objectViewer"
```

別の方法として、**コマンド プロンプト (cmd)** を開いて、上記の `gcloud` コマンドをそのまま実行しても構いません。

付与後、もう一度 `gcloud run deploy --source .` を実行してください。

### 8.4 その他のよくある事象

| 現象 | 確認すること |
|------|----------------|
| デプロイが失敗する | 上記 8.3 の 403（ストレージ）を解消したか確認。API 有効化: `gcloud services enable run.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com`。**「Build failed」と出たら** → 下記 8.5 の手順でビルドログを確認。 |
| ビルドは通るがコンテナが起動しない | Dockerfile のコメントは **半角英数字のみ**にすること（日本語はアップロード後に文字化けしてビルドエラーになることがあります）。 |
| 起動時に CSV がない | ビルドコンテキストに `output/clinics_merged.csv` が含まれているか確認。`.gcloudignore` で `output/` を除外していないか確認。 |
| Vertex AI で 403 / 権限エラー（`aiplatform.endpoints.predict` denied） | 上記「7. 権限」のとおり、Cloud Run のサービスアカウントに「Vertex AI ユーザー」を付与。詳細は下記「8.2 Vertex AI 403」を参照。 |
| ページが真っ白 / 502 | メモリ不足の可能性。`--memory 2Gi` で再デプロイを試す。ログは Cloud Run の「ログ」タブで確認。 |
| 環境変数が効いていない | Cloud Run の「変数とシークレット」で `GOOGLE_CLOUD_PROJECT` が設定されているか確認。変更後は新しいリビジョンがデプロイされるまで数十秒かかることがある。 |

### 8.5 「Build failed」と出たとき（ビルドログの確認）

デプロイ時に「Building Container」のあとで失敗する場合は、**Cloud Build のどのステップで失敗したか**をログで確認します。

**方法 1: コンソールで見る**

1. デプロイ時に表示された **Logs are available at [URL]** のリンクをブラウザで開く。  
2. または [Cloud Build → 履歴](https://console.cloud.google.com/cloud-build/builds) を開き、直近の失敗したビルドをクリック。  
3. 「ログ」または各ステップを開き、**赤い FAILED になったステップ**のログ末尾のエラー文を確認。

**方法 2: コマンドでログを取得（Windows の場合は gcloud.cmd）**

```bash
# ビルド ID はデプロイ時のログ URL の末尾（例: c528e2dd-a372-4b2e-bed8-efdd862d963c）
gcloud builds log BUILD_ID --region=asia-northeast1
```

PowerShell では:

```powershell
gcloud.cmd builds log c528e2dd-a372-4b2e-bed8-efdd862d963c --region=asia-northeast1
```

（`BUILD_ID` は毎回変わるので、**そのときに表示された ID** に置き換えてください。）

**「artifactregistry.repositories.uploadArtifacts denied」と出て PUSH が失敗する場合**

Docker イメージのビルドは成功しているが、Artifact Registry へのプッシュで権限エラーになる場合、Cloud Build を実行しているサービスアカウントに **Artifact Registry への書き込み** を付与します。

PowerShell（`gcloud.cmd` 使用）:

```powershell
$PROJECT_ID = "medigate-ai"
$PN = (gcloud.cmd projects describe $PROJECT_ID --format="value(projectNumber)")
gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${PN}-compute@developer.gserviceaccount.com" --role="roles/artifactregistry.writer"
```

付与後、もう一度 `gcloud.cmd builds submit --config=cloudbuild.yaml . --region=asia-northeast1` を実行してください。

**「does not have permission to write logs to Cloud Logging」と出てビルドが FAILURE になる場合**

Cloud Build を実行しているサービスアカウント（Compute のデフォルト）に **ログ書き込み** 権限を付けます。付与後、同じコマンドでもう一度ビルドを実行してください。

PowerShell（`gcloud.cmd` 使用）:

```powershell
$PROJECT_ID = "medigate-ai"
$PN = (gcloud.cmd projects describe $PROJECT_ID --format="value(projectNumber)")
gcloud.cmd projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${PN}-compute@developer.gserviceaccount.com" --role="roles/logging.logWriter"
```

**「403 Forbidden — Your client does not have permission to get URL」と出る場合**

ブラウザで Cloud Run の URL を開いたときに「Forbidden」になる場合は、**未認証ユーザー（誰でも）がサービスを呼び出せる**ように IAM を設定します。次のコマンドで **Cloud Run Invoker** を `allUsers` に付与してください。

PowerShell（Windows の場合は `gcloud.cmd`）:

```powershell
gcloud.cmd run services add-iam-policy-binding medigate-ai --region=asia-northeast1 --member="allUsers" --role="roles/run.invoker"
```

プロジェクト ID が `medigate-ai` 以外の場合は、サービス名 `medigate-ai` はそのままで問題ありません（サービス名はデプロイ時に付けた名前）。実行後、**「y」でポリシーの更新を承認**し、数秒待ってから再度 URL にアクセスしてください。

**「FAILED_PRECONDITION: One or more users named in the policy do not belong to a permitted customer」と出る場合**

組織ポリシーで **allUsers（誰でもアクセス）** の IAM 付与が禁止されているため、上記の `add-iam-policy-binding ... allUsers` が実行できません。**組織ポリシーを触らずに**、Cloud Run 側の設定だけで「誰でもアクセス可」にする方法があります。

**推奨: Invoker IAM チェックを無効にする（組織ポリシーの変更不要）**

IAM で `allUsers` を追加する代わりに、**「Invoker の IAM チェックを行わない」**設定にすると、同じように誰でも URL にアクセスできます。組織ポリシーで allUsers が禁止されていても利用できます。

**方法 1: コンソール**

1. [Cloud Run](https://console.cloud.google.com/run) を開く  
2. リージョン **asia-northeast1** を選択  
3. サービス **medigate-ai** の**名前をクリック**（行のチェックボックスではなく）  
4. 上部タブの **「セキュリティ」**（Security）をクリック  
5. **「認証されていないアクセスを許可」**（Allow public access）を選択  
6. **「保存」**（Save）をクリック  

**方法 2: コマンド**

PowerShell（`gcloud.cmd` 使用）:

```powershell
gcloud.cmd run services update medigate-ai --region=asia-northeast1 --no-invoker-iam-check
```

実行後、数秒待ってからサービス URL をブラウザで開き直してください。

---

**組織ポリシーを確認・変更する場合（管理者向け）**

「Invoker IAM チェックを無効にする」ではなく、従来どおり IAM で allUsers を許可したい場合は、組織の管理者が組織ポリシーを変更する必要があります。

- **組織ポリシーの開き方**: コンソール左上の **ナビゲーションメニュー（≡）** → **「IAM と管理」** → **「組織のポリシー」**。または [このリンク](https://console.cloud.google.com/iam-admin/orgpolicies) を開き、画面上部のプロジェクト選択で **組織** または **フォルダ** を選ぶと、その階層で有効なポリシー一覧が表示されます。
- 制約の**表示名**は組織や言語設定により異なります（例: 「ドメイン制限付き共有」「Domain restricted sharing」など）。一覧の制約を開いて「ポリシーを適用」がオンになっているか、**許可するプリンシパル**に allUsers や「すべてのユーザー」を追加できるかを確認してください。制約 ID の例: `iam.allowedPolicyMemberDomains`（ドメイン制限）。

**認証付きで動作確認だけする場合**

サービスが動いているか **コマンドで確認**するには、自分の ID トークン付きでリクエストします。

```powershell
$URL = (gcloud.cmd run services describe medigate-ai --region=asia-northeast1 --format="value(status.url)")
$TOKEN = (gcloud.cmd auth print-identity-token)
Invoke-WebRequest -Uri $URL -Headers @{ Authorization = "Bearer $TOKEN" } -UseBasicParsing | Select-Object -ExpandProperty Content
```

HTML が返ればサービスは稼働しています。

**「このビルドまたはステップのログは見つかりませんでした」と出る場合**

- **権限**: プロジェクトで「ログの閲覧者」ロール（`roles/logging.viewer`）が付与されているか確認してください。IAM で自分のアカウントに `logging.viewer` を追加すると、次回からログが見られることがあります。
- **有効期限**: ログはデフォルトで 30 日で消えます。古いビルドのログは見られないことがあります。
- **ローカルで同じビルドを再現する**: 下記「8.6 ローカルで Docker ビルドしてエラーを確認する」で、Cloud Build と同じ内容を自分の PC で実行し、エラー内容を確認できます。

### 8.6 ローカルで Docker ビルドしてエラーを確認する

Cloud のログが見られない場合、**同じ Dockerfile でローカルビルド**すると、同じエラーをその場で確認できます（Docker Desktop などが入っている場合）。

```bash
cd C:\Users\admin\medigate-ai
docker build -t medigate-ai-test .
```

ここで失敗したら、ターミナルに表示される**最後の数行のエラーメッセージ**を控えてください。その内容で原因を特定できます。  
（成功した場合は、Cloud Build 側の権限・リソース・ログ保持の可能性が高いです。）

**よくある原因と対処**

| ログの内容 | 対処 |
|------------|------|
| `pip install` でエラー（例: コンパイル失敗） | `Dockerfile` で `gcc` を入れているので多くの場合は解消済み。特定パッケージで失敗している場合は `requirements.txt` のバージョンを固定する。 |
| メモリ不足 / ビルドがタイムアウト | ビルド用にマシンタイプを上げる（下記「ビルドのタイムアウト・メモリ」参照）。 |
| `COPY . .` でファイルがない | `.gcloudignore` で `app.py` や `services/` を除外していないか確認。 |

**ビルドのタイムアウト・メモリを変更する（2段階デプロイ）**

プロジェクトには **`cloudbuild.yaml`** を用意してあります（タイムアウト 20 分・マシン E2_HIGHCPU_8）。**「Build failed」でログも見られず Docker も使わない場合**は、次の **2段階デプロイ** を試してください。

---

### 8.7 2段階デプロイ（ビルドだけ先に実行する）

`gcloud run deploy --source .` のビルドが失敗するとき、**先に Cloud Build だけ**実行し、成功したイメージを **そのあと** Cloud Run にデプロイする方法です。`cloudbuild.yaml` でタイムアウトとマシンサイズを指定しているため、ビルドが通りやすくなります。

**Step 1: イメージをビルドして Artifact Registry にプッシュ**

PowerShell（Windows）では `gcloud.cmd` を使ってください。

```powershell
cd C:\Users\admin\medigate-ai
gcloud.cmd builds submit --config=cloudbuild.yaml . --region=asia-northeast1
```

成功すると「DONE」と表示され、イメージが `asia-northeast1-docker.pkg.dev/medigate-ai/cloud-run-source-deploy/medigate-ai:latest` にプッシュされます。

**Step 2: そのイメージで Cloud Run にデプロイ**

```powershell
gcloud.cmd run deploy medigate-ai --image asia-northeast1-docker.pkg.dev/medigate-ai/cloud-run-source-deploy/medigate-ai:latest --region asia-northeast1 --allow-unauthenticated --set-env-vars "GOOGLE_CLOUD_PROJECT=medigate-ai,VERTEX_LOCATION=asia-northeast1"
```

（プロジェクト ID が `medigate-ai` 以外の場合は、上記の `medigate-ai` を実際のプロジェクト ID に置き換えてください。）

この 2段階なら、**Step 1 で失敗した場合に Cloud Build のコンソールでビルドログを確認**しやすくなります（ビルド履歴から該当ビルドを開いてログを表示）。

---

### 再デプロイの手順（コード変更を反映するとき）

すでに 2段階デプロイで一度デプロイ済みの場合、**同じ 2 ステップを再度実行**すれば最新のコードが反映されます。プロジェクトルートで以下を順に実行してください。

**Step 1: イメージを再ビルドしてプッシュ**

```powershell
cd C:\Users\admin\medigate-ai
gcloud.cmd builds submit --config=cloudbuild.yaml . --region=asia-northeast1
```

**Step 2: 新しいイメージで Cloud Run を更新**

```powershell
gcloud.cmd run deploy medigate-ai --image asia-northeast1-docker.pkg.dev/medigate-ai/cloud-run-source-deploy/medigate-ai:latest --region asia-northeast1 --allow-unauthenticated --set-env-vars "GOOGLE_CLOUD_PROJECT=medigate-ai,VERTEX_LOCATION=asia-northeast1"
```

- 以前「403 Forbidden」対策で **Invoker IAM チェックを無効**（`--no-invoker-iam-check`）にしている場合は、上記の `run deploy` の末尾に `--no-invoker-iam-check` を追加してください。
- プロジェクト ID が `medigate-ai` 以外の場合は、`medigate-ai` を実際のプロジェクト ID に置き換えてください。

完了後、表示される **Service URL** で動作を確認してください。

---

### 「医療機関を表示する画面で最初の画面に戻ってしまう」場合

Cloud Run では**リクエストのたびに別インスタンスに振られる**ことがあり、その際に **Streamlit のセッション（入力内容や step）が消える**ことがあります。その結果、医療機関一覧まで進んだあとで「最初の画面」に戻ったように見えます。

**今回の対応（アプリ側）**

- 画面の step を URL のクエリパラメータ（`?step=2` / `?step=3`）にも持たせるようにしました。
- セッションが消えているのに URL に `step=2` や `step=3` が残っている場合は「前のセッションが切れました」と表示し、「最初からやり直す」で戻れるようにしました。

**運用で軽減する場合**

- Cloud Run の **「最小インスタンス数」を 1 にすると**、常に 1 台が起動したままになり、同じインスタンスに乗り続けやすくなり、セッションが消えにくくなります（課金は増えます）。コンソールで Cloud Run サービス → 編集 → 「最小インスタンス数」を 1 に設定できます。

---

## 9. コマンド一覧（まとめ）

```bash
# 1. ログイン・プロジェクト設定
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 2. API 有効化
gcloud services enable run.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com

# 3. デプロイ（環境変数付き）
cd /path/to/medigate-ai
gcloud run deploy medigate-ai \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,VERTEX_LOCATION=asia-northeast1"
```

デプロイ完了後、表示された **Service URL** にアクセスして動作を確認してください。

---

## 10. デプロイ後の URL の確認

**表示用 URL（アプリのアドレス）** は次のいずれかで確認できます。

### 方法 1: デプロイ完了時のターミナル

`gcloud run deploy` または `gcloud builds submit` のあとに `gcloud run deploy ... --image=...` を実行したとき、成功メッセージに **Service URL** が表示されます。

```text
Service [medigate-ai] revision [medigate-ai-xxxxx] has been deployed and is serving 100 percent of traffic.
Service URL: https://medigate-ai-xxxxxxxx-an.a.run.app
```

この **Service URL** がアプリの表示用 URL です。

### 方法 2: コマンドで取得

PowerShell（Windows の場合は `gcloud.cmd`）:

```powershell
gcloud.cmd run services describe medigate-ai --region=asia-northeast1 --format="value(status.url)"
```

表示された 1 行（`https://...run.app`）がサービス URL です。

### 方法 3: コンソールで確認

1. [Cloud Run コンソール](https://console.cloud.google.com/run) を開く  
2. リージョンで **asia-northeast1** を選択  
3. サービス一覧から **medigate-ai** をクリック  
4. 画面上部の **「URL」** または **「このリビジョンの URL」** が表示用 URL です  

---

## 11. GitHub へのアップロード

リポジトリを GitHub に上げる手順です（初回のみ。既にリモートがある場合は 11.3 の push だけ実行）。

### 11.1 注意（.env は上げない）

`.env` は `.gitignore` に含まれているため、**Git にはコミットされません**（API キーやプロジェクト ID が GitHub に載らないようにするため）。GitHub に上げたあと、別の環境で動かす場合は、その環境で `.env` を用意するか、Cloud Run の「変数とシークレット」で設定してください。

### 11.2 初回: リポジトリの用意とプッシュ

Git がまだ初期化されていない場合:

```powershell
cd C:\Users\admin\medigate-ai
git init
git add .
git commit -m "Initial commit: MediGate AI MVP"
```

GitHub で **New repository** からリポジトリ（例: `medigate-ai`）を作成し、**空のまま**作成します。その後:

```powershell
git remote add origin https://github.com/あなたのユーザー名/medigate-ai.git
git branch -M main
git push -u origin main
```

（`あなたのユーザー名/medigate-ai` は実際の GitHub のユーザー名とリポジトリ名に置き換えてください。SSH を使う場合は `git@github.com:ユーザー名/medigate-ai.git` でも可。）

### 11.3 すでにリモートがある場合

```powershell
cd C:\Users\admin\medigate-ai
git add .
git commit -m "メッセージ"
git push origin main
```

### 11.4 大きなファイル（output/clinics_merged.csv）について

`output/clinics_merged.csv` は 70,000 行以上あるため、GitHub にプッシュするとリポジトリが大きくなります。必要なら `.gitignore` に `output/` を追加して CSV を除外し、代わりに「CSV の取得方法」を README に書いておく方法もあります。Cloud Run のイメージにはビルド時に含めているので、デプロイには影響しません。
