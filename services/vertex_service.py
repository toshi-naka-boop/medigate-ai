"""
Vertex AI (Gemini) を用いた症状分析・推奨科・PQRSTメモ生成
"""
import vertexai
from vertexai.generative_models import GenerativeModel
import os
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel

load_dotenv(override=True)

def _get_model(project_id: str | None = None, location: str | None = None):
    project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = location or os.getenv("VERTEX_LOCATION", "asia-northeast1")
    model_id = os.getenv("VERTEX_MODEL_ID", "gemini-2.5-flash")
    # Vertex のモデル ID 末尾 -001 は省略して指定する（例: gemini-2.0-flash）
    if model_id.endswith("-001"):
        model_id = model_id[:-4]

    vertexai.init(project=project_id, location=location)
    return GenerativeModel(model_id)


def generate_followup_questions(
    project_id: str,
    symptom: str,
    location: str = "us-central1",
) -> str:
    """
    症状から追加で確認すべき質問を2〜5個生成
    """
    model = _get_model(project_id, location)
    prompt = f"""あなたは患者の症状を詳しく把握するための質問を考える医療アシスタントです。
患者が「{symptom}」と訴えています。
診断はせず、症状をより正確に把握するために医師が確認すべき追加質問を2〜5個、箇条書きで出力してください。
各質問は1行で、番号をつけてください。
日本語で出力してください。"""
    response = model.generate_content(prompt)
    return response.text.strip() if response.text else ""


def generate_department_recommendation(
    project_id: str,
    symptom: str,
    additional_answers: str,
    location: str = "us-central1",
) -> tuple[str, str]:
    """
    症状と追加回答から推奨科と非診断の説明文を生成
    Returns: (推奨科の説明, 非診断の注意書き)
    """
    model = _get_model(project_id, location)
    prompt = f"""あなたは適切な診療科を案内する医療ナビゲーターです。
患者の訴え: {symptom}
追加情報: {additional_answers}

以下の2つを出力してください。診断は絶対にしないでください。

【推奨する診療科】
上記情報に基づき、受診を推奨する診療科を1〜3つ、理由とともに箇条書きで示してください。

【重要な注意】
「このシステムは診断を行いません。正確な診断は医師の診察が必要です。」という旨を、
患者向けに分かりやすい日本語で1〜2文で記載してください。"""
    response = model.generate_content(prompt)
    text = response.text.strip() if response.text else ""
    parts = text.split("【重要な注意】")
    recommendation = parts[0].replace("【推奨する診療科】", "").strip() if parts else text
    disclaimer = parts[1].strip() if len(parts) > 1 else ""
    return recommendation, disclaimer


def generate_pqrst_notes(
    project_id: str,
    symptom: str,
    additional_answers: str,
    location: str = "us-central1",
) -> str:
    """
    症状と追加回答から PQRST 形式の医師向けメモを生成
    P: Provocation/Palliation (誘発・軽減要因)
    Q: Quality (性質)
    R: Region/Radiation (部位・放散)
    S: Severity (重症度)
    T: Timing (発症・持続時間)
    """
    model = _get_model(project_id, location)
    prompt = f"""あなたは医師の診察を補助するメモを作成するアシスタントです。
以下の患者情報から、医師が診察時に参照するPQRST形式のメモを作成してください。

患者の訴え: {symptom}
追加情報: {additional_answers}

PQRST形式で以下の項目に沿って整理してください。情報が不明な項目は「不明」と記載してください。
- P (誘発・軽減要因): 何をすると悪化/軽減するか
- Q (性質): 症状の性質（鋭い、鈍い、ズキズキ等）
- R (部位・放散): 症状の部位と放散の有無
- S (重症度): 重症度の目安（1-10 scale等）
- T (発症・持続時間): いつから、どれくらい続いているか

日本語で、医師向けの簡潔なメモとして出力してください。"""
    response = model.generate_content(prompt)
    return response.text.strip() if response.text else ""
