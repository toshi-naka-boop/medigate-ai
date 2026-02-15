# -*- coding: utf-8 -*-
"""
専門医・認定医などの情報をウェブ検索（Google Search グラウンディング）で取得し、ソース付きで返す。
google-genai SDK の Vertex AI + Google Search を使用。
"""
from __future__ import annotations

from typing import Optional

# google-genai は google-cloud-aiplatform に含まれる場合あり
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


def search_specialist_info_with_sources(
    project_id: str,
    clinic_name: str,
    clinic_url: Optional[str] = None,
    departments: Optional[str] = None,
    location: str = "asia-northeast1",
) -> tuple[str, list[dict]]:
    """
    医療機関の専門医・認定医・学会認定などの情報をウェブ検索で調べ、ソースURL付きで返す。

    Returns:
        (要約テキスト, ソースのリスト [{"title": str, "uri": str}, ...])
    """
    if genai is None or types is None:
        return "google-genai がインストールされていません。pip install google-genai を実行してください。", []

    prompt = f"""以下の医療機関について、専門医・認定医・学会認定・指導医などの情報をウェブで調べ、ソース（参照したURL）を明示できる形で簡潔にまとめてください。

- 医療機関名: {clinic_name}
- 公式HP: {clinic_url or '不明'}
- 標ぼう科目: {departments or '不明'}

ルール:
- 見つかった情報は箇条書きで、どのサイトの情報か分かるように記載してください。
- 情報がまったく見つからない場合は「公表されている専門医・認定医の情報は見つかりませんでした」と記載してください。
- 推測や創作はせず、検索結果に基づく事実のみを記載してください。
- 日本語で回答してください。"""

    try:
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=1.0,
            ),
        )
    except Exception as e:
        return f"検索中にエラーが発生しました: {e}", []

    text = (getattr(response, "text", None) or "").strip() if response else ""
    if not text and response and response.candidates:
        cand = response.candidates[0]
        if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
            for part in cand.content.parts:
                if getattr(part, "text", None):
                    text = part.text.strip()
                    break

    sources: list[dict] = []
    if response and response.candidates:
        cand = response.candidates[0]
        meta = getattr(cand, "grounding_metadata", None)
        if meta and getattr(meta, "grounding_chunks", None):
            for chunk in meta.grounding_chunks:
                web = getattr(chunk, "web", None)
                if web and (getattr(web, "uri", None) or getattr(web, "title", None)):
                    sources.append({
                        "title": getattr(web, "title", None) or getattr(web, "uri", "") or "(無題)",
                        "uri": getattr(web, "uri", None) or "",
                    })

    return (text or "情報を取得できませんでした。"), sources
