"""
MediGate AI - 症状から適切な医療機関を案内するMVP
"""
import os
import streamlit as st
from dotenv import load_dotenv

from services.places_service import get_medical_facilities_near_kashiwa
from services.vertex_service import (
    generate_followup_questions,
    generate_department_recommendation,
    generate_pqrst_notes,
)

load_dotenv()

# 環境変数
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")

st.set_page_config(
    page_title="MediGate AI",
    page_icon="🏥",
    layout="wide",
)

# セッション状態の初期化
if "symptom" not in st.session_state:
    st.session_state.symptom = ""
if "additional_answers" not in st.session_state:
    st.session_state.additional_answers = ""
if "followup_questions" not in st.session_state:
    st.session_state.followup_questions = ""
if "recommendation" not in st.session_state:
    st.session_state.recommendation = ""
if "disclaimer" not in st.session_state:
    st.session_state.disclaimer = ""
if "facilities" not in st.session_state:
    st.session_state.facilities = []
if "pqrst_notes" not in st.session_state:
    st.session_state.pqrst_notes = ""
if "step" not in st.session_state:
    st.session_state.step = 1
if "step3_loaded" not in st.session_state:
    st.session_state.step3_loaded = False


def render_header():
    st.title("🏥 MediGate AI")
    st.caption("症状を入力すると、適切な診療科と近くの医療機関をご案内します（診断は行いません）")


def render_symptom_input():
    st.header("1️⃣ 症状の入力")
    symptom = st.text_area(
        "どのような症状がありますか？",
        placeholder="例：頭が痛い、発熱が3日続いている、咳と鼻水が出る など",
        height=100,
    )
    if st.button("次へ（追加質問を生成）", type="primary"):
        if not symptom.strip():
            st.error("症状を入力してください")
            return
        if not GOOGLE_CLOUD_PROJECT:
            st.error("GOOGLE_CLOUD_PROJECT が設定されていません")
            return
        with st.spinner("追加の質問を生成しています..."):
            try:
                questions = generate_followup_questions(
                    GOOGLE_CLOUD_PROJECT,
                    symptom.strip(),
                    VERTEX_LOCATION,
                )
                st.session_state.symptom = symptom.strip()
                st.session_state.followup_questions = questions
                st.session_state.step = 2
                st.rerun()
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")


def render_additional_questions():
    st.header("2️⃣ 追加の質問")
    st.info("より適切な案内のため、以下の質問にお答えください")
    st.markdown(st.session_state.followup_questions)
    additional_answers = st.text_area(
        "上記の質問への回答を自由に記入してください",
        placeholder="各質問に対する回答を記入",
        height=150,
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("戻る"):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("推奨科と医療機関を表示", type="primary"):
            st.session_state.additional_answers = additional_answers.strip()
            st.session_state.step = 3
            st.rerun()


def render_recommendation_and_facilities():
    st.header("3️⃣ 推奨する診療科")
    if not GOOGLE_CLOUD_PROJECT or not GOOGLE_PLACES_API_KEY:
        st.error("GOOGLE_CLOUD_PROJECT と GOOGLE_PLACES_API_KEY を設定してください")
        return

    if not st.session_state.step3_loaded:
        with st.spinner("推奨科と医療機関を取得しています..."):
            try:
                recommendation, disclaimer = generate_department_recommendation(
                    GOOGLE_CLOUD_PROJECT,
                    st.session_state.symptom,
                    st.session_state.additional_answers,
                    VERTEX_LOCATION,
                )
                st.session_state.recommendation = recommendation
                st.session_state.disclaimer = disclaimer
            except Exception as e:
                st.error(f"推奨科の生成に失敗しました: {e}")
                return

            try:
                facilities = get_medical_facilities_near_kashiwa(
                    GOOGLE_PLACES_API_KEY,
                    max_results=10,
                )
                st.session_state.facilities = facilities
            except Exception as e:
                st.warning(f"医療機関の取得に失敗しました: {e}")
                st.session_state.facilities = []

            try:
                pqrst = generate_pqrst_notes(
                    GOOGLE_CLOUD_PROJECT,
                    st.session_state.symptom,
                    st.session_state.additional_answers,
                    VERTEX_LOCATION,
                )
                st.session_state.pqrst_notes = pqrst
            except Exception as e:
                st.session_state.pqrst_notes = ""
            st.session_state.step3_loaded = True

    st.markdown(st.session_state.recommendation)
    st.warning(st.session_state.disclaimer)

    st.header("4️⃣ 柏駅周辺の医療機関")
    if not st.session_state.facilities:
        st.info("該当する医療機関が見つかりませんでした")
    else:
        for i, f in enumerate(st.session_state.facilities, 1):
            with st.expander(f"**{i}. {f['name']}**", expanded=(i <= 3)):
                st.write(f"📍 {f['address']}")
                if f.get("open_now") is not None:
                    status = "🟢 営業中" if f["open_now"] else "🔴 営業時間外"
                    st.write(status)
                if f.get("opening_hours"):
                    st.write("**営業時間**")
                    for line in f["opening_hours"][:7]:
                        st.write(f"  {line}")
                if f.get("website"):
                    st.write(f"🔗 [公式サイト]({f['website']})")
                st.caption(f"Place ID: {f['place_id']}")

    st.header("5️⃣ 医師向けメモ（PQRST）")
    if st.session_state.pqrst_notes:
        st.code(st.session_state.pqrst_notes, language=None)
    else:
        st.info("PQRSTメモを生成できませんでした")

    if st.button("最初からやり直す"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.step = 1
        st.session_state.step3_loaded = False
        st.rerun()


def main():
    render_header()

    if st.session_state.step == 1:
        render_symptom_input()
    elif st.session_state.step == 2:
        render_additional_questions()
    elif st.session_state.step == 3:
        render_recommendation_and_facilities()


if __name__ == "__main__":
    main()
