"""
MediGate AI - ローカルMVP
- 症状入力 → 追加質問 → 推奨診療科（Vertex AI / Gemini） → 近隣クリニック検索（CSV）
- 起点：現在地（ブラウザ）＋ 指定駅（田町/上野/柏）
- 受付状況：受付中/もうすぐ終了/受付外/不明（services側で計算）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from streamlit_js_eval import get_geolocation

from services.vertex_service import (
    generate_followup_questions,
    generate_department_recommendation,
    generate_pqrst_notes,
)

from services.clinic_dataset_service import (
    load_clinic_dataset,
    search_clinics_near_point,
)

from services.specialist_search_service import search_specialist_info_with_sources
from services.stations import STATIONS


# -------------------------
# Env
# -------------------------
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=str(ENV_PATH), override=True)

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "asia-northeast1")  # あなたの環境に合わせて東京既定

ORIGIN_CURRENT = "現在地（ブラウザ）"
REQUIRED_STATIONS = ["田町駅", "上野駅", "柏駅"]


# -------------------------
# Streamlit config
# -------------------------
st.set_page_config(
    page_title="MediGate AI",
    page_icon="🏥",
    layout="wide",
)

# -------------------------
# Session state init
# -------------------------
def _init_state():
    ss = st.session_state
    ss.setdefault("symptom", "")
    ss.setdefault("additional_answers", "")
    ss.setdefault("followup_questions", "")
    ss.setdefault("recommendation", "")
    ss.setdefault("disclaimer", "")
    ss.setdefault("pqrst_notes", "")
    ss.setdefault("step", 1)
    ss.setdefault("step3_loaded", False)

    # Cloud Run などでインスタンスが切り替わるとセッションが消えることがある。
    # URL の step から復元を試みる（中身はないので「セッション切れ」メッセージを出す）
    qp = st.query_params.get("step")
    if qp and qp.isdigit():
        qp_step = int(qp)
        if qp_step in (2, 3) and not ss.get("symptom", "").strip():
            ss["step"] = qp_step
            ss["_session_expired"] = True

_init_state()


# -------------------------
# Helpers
# -------------------------
@st.cache_data(show_spinner=False)
def _load_dataset_cached():
    return load_clinic_dataset()


def render_header():
    st.title("🏥 MediGate AI")
    st.caption("症状を入力すると、適切な診療科と近くのクリニックをご案内します（診断は行いません）")


def get_current_latlng() -> Tuple[Optional[float], Optional[float]]:
    """
    ブラウザの現在地を取得。取得できなければ (None, None) を返す。
    ※ HTTPS または localhost で動作。ブラウザで位置情報を許可してください。
    """
    loc = get_geolocation()

    if not loc:
        return None, None

    if isinstance(loc, dict) and loc.get("error"):
        return None, None

    # coords 内またはトップレベル (streamlit_js_eval の戻り形式に両対応)
    coords = loc.get("coords") if isinstance(loc, dict) else {}
    if not isinstance(coords, dict):
        coords = {}
    lat = coords.get("latitude") if coords else None
    lng = coords.get("longitude") if coords else None
    if lat is None and isinstance(loc, dict):
        lat = loc.get("latitude")
        lng = loc.get("longitude")

    if lat is None or lng is None:
        return None, None

    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None, None


def _guess_dept_keywords_from_text(recommendation_text: str) -> List[str]:
    """
    推奨文から診療科キーワードを雑に推定（MVP用）
    ※本来は Vertex 側でJSON等を返すのが理想。
    """
    t = (recommendation_text or "").replace(" ", "").replace("　", "")

    candidates = [
        "内科", "呼吸器内科", "消化器内科", "循環器内科", "腎臓内科",
        "小児科", "耳鼻咽喉科", "皮膚科", "整形外科", "外科",
        "婦人科", "泌尿器科", "眼科", "脳神経外科",
        "心療内科", "精神科",
    ]
    hit = [c for c in candidates if c in t]
    return hit or ["内科"]


def _build_exclude_depts(dept_keywords: List[str]) -> List[str]:
    """
    内科検索に心療内科が混ざる問題への簡易対処。
    ただし推奨がメンタル系なら除外しない。
    """
    dept_keywords = dept_keywords or []
    mental = {"心療内科", "精神科", "メンタル"}
    if any(k in mental for k in dept_keywords):
        return []
    return ["心療内科", "精神科", "メンタル"]


def _pick_first(row: dict, keys: List[str], default: str = "") -> str:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return default


def _render_map_if_possible(df_out):
    """緯度経度があれば st.map を出す（無ければ何もしない）"""
    if df_out is None or getattr(df_out, "empty", True):
        return

    possible_lat = ["所在地座標（緯度）", "緯度", "lat", "latitude"]
    possible_lng = ["所在地座標（経度）", "経度", "lng", "lon", "longitude"]

    lat_col = next((c for c in possible_lat if c in df_out.columns), None)
    lng_col = next((c for c in possible_lng if c in df_out.columns), None)
    if not lat_col or not lng_col:
        return

    tmp = df_out[[lat_col, lng_col]].copy()
    tmp.columns = ["lat", "lon"]
    tmp = tmp.dropna()
    if tmp.empty:
        return

    with st.expander("🗺️ 地図で表示", expanded=False):
        st.map(tmp)


def _render_results_block(
    origin_label: str,
    df,
    base_lat: float,
    base_lng: float,
    radius_km: float,
    dept_keywords: List[str],
    exclude_name_keywords: List[str],
    only_accepting_now: bool,
    soon_close_threshold_min: int,
    limit: int,
):
    exclude_dept_keywords = _build_exclude_depts(dept_keywords)

    out = search_clinics_near_point(
        df,
        base_lat,
        base_lng,
        radius_km=radius_km,
        dept_keyword=dept_keywords,
        exclude_dept_keywords=exclude_dept_keywords if exclude_dept_keywords else None,
        exclude_name_keywords=exclude_name_keywords,
        only_accepting_now=only_accepting_now,
        soon_close_threshold_min=soon_close_threshold_min,
        limit=limit,
    )

    if out is None or out.empty:
        st.info("近くのクリニックが見つかりませんでした。条件を緩めて試してください。")
        return

    _render_map_if_possible(out)

    for i, row in enumerate(out.to_dict(orient="records"), 1):
        name = _pick_first(row, ["正式名称", "医療機関名称", "医療機関名", "名称", "name"], default="（名称不明）")
        addr = _pick_first(row, ["住所", "所在地", "所在地住所", "所在地_住所", "所在地（住所）"])
        dept = _pick_first(row, ["標ぼう科目_一覧", "標ぼう科目_一覧_主要", "標榜科目", "診療科"])
        status = str(row.get("reception_status", "")).strip()
        next_label = str(row.get("next_reception_label", "")).strip()
        dist = row.get("distance_km", None)
        url = _pick_first(row, ["案内用ホームページアドレス", "ホームページ", "URL", "url"])

        header = f"**{i}. {name}**"
        if status:
            header += f"  —  {status}"

        with st.expander(header, expanded=(i <= 3)):
            if addr:
                st.write(f"📍 {addr}")
            if dept:
                st.write(f"🏷️ 標ぼう科目: {dept}")
            if next_label:
                st.write(f"➡️ 次回受付開始: {next_label}")
            if dist is not None:
                try:
                    st.write(f"📏 距離: {float(dist):.2f} km")
                except Exception:
                    pass
            if url:
                # link_button が使える場合はボタン、無ければリンク表示
                try:
                    st.link_button("公式サイトを開く", url)
                except Exception:
                    st.markdown(f"- 公式サイト: {url}")

            # 専門医・認定医などの情報（ウェブ検索・ソース付き）
            st.markdown("---")
            st.caption("専門医・認定医・学会認定などの情報をウェブから検索（ソース付き）")
            clinic_id = str(row.get("ID", "") or f"{origin_label}_{i}")
            cache_key = f"specialist_{clinic_id}"
            if st.button("専門医情報をウェブ検索", key=f"btn_spec_{clinic_id}_{i}"):
                with st.spinner("検索中..."):
                    summary, sources = search_specialist_info_with_sources(
                        project_id=GOOGLE_CLOUD_PROJECT or "",
                        clinic_name=name,
                        clinic_url=url or None,
                        departments=dept or None,
                        location=VERTEX_LOCATION,
                    )
                    st.session_state[cache_key] = (summary, sources)
            if cache_key in st.session_state:
                summary, sources = st.session_state[cache_key]
                st.markdown(summary)
                if sources:
                    st.caption("参照したソース:")
                    for s in sources:
                        uri = s.get("uri", "").strip()
                        title = (s.get("title") or uri or "(無題)").strip()
                        if uri:
                            st.markdown(f"- [{title}]({uri})")
                        else:
                            st.markdown(f"- {title}")

            st.caption(f"検索起点: {origin_label} / ID: {row.get('ID','')}")


# -------------------------
# Step 1: symptom input
# -------------------------
def render_symptom_input():
    st.header("1. 症状入力")

    symptom = st.text_area(
        "どのような症状がありますか？（できる範囲で具体的に）",
        placeholder="例：3日前から喉が痛い。熱は37.8℃。咳が少し出る。息苦しさはない。",
        height=120,
    )

    if st.button("次へ（追加質問を生成）", type="primary"):
        if not symptom.strip():
            st.error("症状を入力してください。")
            return
        if not GOOGLE_CLOUD_PROJECT:
            st.error("GOOGLE_CLOUD_PROJECT が未設定です。.env を確認してください。")
            return

        with st.spinner("追加質問を生成しています..."):
            try:
                questions = generate_followup_questions(
                    GOOGLE_CLOUD_PROJECT,
                    symptom.strip(),
                    VERTEX_LOCATION,
                )
                st.session_state.symptom = symptom.strip()
                st.session_state.followup_questions = questions
                st.session_state.step = 2
                st.query_params["step"] = "2"
                st.rerun()
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")


# -------------------------
# Step 2: additional answers
# -------------------------
def render_additional_questions():
    st.header("2. 追加質問への回答")
    st.info("より適切な診療科を提案するため、以下の質問に分かる範囲で回答してください。")

    st.markdown(st.session_state.followup_questions or "（追加質問がありません）")

    additional_answers = st.text_area(
        "回答（箇条書きでもOK）",
        placeholder="例：熱は今朝37.6℃。喉の痛みは飲み込むとき強い。既往歴なし。",
        height=160,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("戻る"):
            st.session_state.step = 1
            if "step" in st.query_params:
                del st.query_params["step"]
            st.rerun()
    with col2:
        if st.button("次へ（推奨診療科を生成）", type="primary"):
            st.session_state.additional_answers = (additional_answers or "").strip()
            st.session_state.step = 3
            st.query_params["step"] = "3"
            st.rerun()


# -------------------------
# Step 3/4/5: recommendation + clinics + pqrst
# -------------------------
def render_recommendation_and_clinics():
    st.header("3. 推奨診療科")

    if not GOOGLE_CLOUD_PROJECT:
        st.error("GOOGLE_CLOUD_PROJECT が未設定です。.env を確認してください。")
        return

    if not st.session_state.step3_loaded:
        with st.spinner("推奨診療科とPQRSTメモを生成しています..."):
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
                st.error(f"推奨生成でエラーが発生しました: {e}")
                return

            try:
                pqrst = generate_pqrst_notes(
                    GOOGLE_CLOUD_PROJECT,
                    st.session_state.symptom,
                    st.session_state.additional_answers,
                    VERTEX_LOCATION,
                )
                st.session_state.pqrst_notes = pqrst
            except Exception:
                st.session_state.pqrst_notes = ""

            st.session_state.step3_loaded = True

    st.markdown(st.session_state.recommendation or "")
    if st.session_state.disclaimer:
        st.warning(st.session_state.disclaimer)

    # ---- 4) Clinics ----
    st.header("4. 近くのクリニック（駅 / 現在地）")

    missing = [s for s in REQUIRED_STATIONS if s not in STATIONS]
    if missing:
        st.error(
            "stations.py に以下が不足しています: "
            + ", ".join(missing)
            + "\nservices/stations.py の STATIONS に駅名→(lat,lng) を追加してください。"
        )
        return

    colA, colB, colC, colD = st.columns([1.2, 1.0, 1.2, 1.0])
    with colA:
        radius_km = st.slider("検索半径 (km)", min_value=0.5, max_value=5.0, value=2.0, step=0.5)
    with colB:
        only_accepting_now = st.checkbox("受付中のみ表示", value=False)
    with colC:
        soon_close_threshold_min = st.slider("『もうすぐ終了』の閾値（分）", min_value=5, max_value=90, value=30, step=5)
    with colD:
        limit = st.selectbox("表示件数", [5, 10, 20], index=1)

    dept_keywords = _guess_dept_keywords_from_text(st.session_state.recommendation)
    exclude_name_keywords = ["在宅", "訪問", "ホームケア"]  # 訪問診療っぽい名称を除外
    st.caption(f"診療科キーワード（推定）: {', '.join(dept_keywords)}")

    origin_options = [ORIGIN_CURRENT] + REQUIRED_STATIONS
    default_origins = [ORIGIN_CURRENT] + REQUIRED_STATIONS

    stations_selected = st.multiselect(
        "検索起点を選択（複数可）",
        options=origin_options,
        default=default_origins,
    )

    if not stations_selected:
        st.info("検索起点を1つ以上選択してください。")
        return

    current_latlng = (None, None)
    if ORIGIN_CURRENT in stations_selected:
        st.caption("※ 現在地を使うには **HTTPS** または **localhost** で開き、ブラウザの位置情報を「許可」にしてください。")
        with st.spinner("現在地を取得しています...（許可ダイアログが出たら「許可」を押してください）"):
            current_latlng = get_current_latlng()

        if current_latlng == (None, None):
            st.warning(
                "現在地を取得できませんでした。駅起点のみで続行します。"
                " ブラウザの位置情報が「許可」になっているか、アドレスバー左の鍵マークから確認してみてください。"
            )
            stations_selected = [x for x in stations_selected if x != ORIGIN_CURRENT]

    if not stations_selected:
        st.info("駅を1つ以上選択してください。")
        return

    merge_view = st.checkbox("起点をまとめて表示（マージ表示）", value=False)

    df = _load_dataset_cached()

    if merge_view:
        merged_rows = []
        for origin in stations_selected:
            if origin == ORIGIN_CURRENT:
                base_lat, base_lng = current_latlng
            else:
                base_lat, base_lng = STATIONS[origin]

            out = search_clinics_near_point(
                df,
                base_lat,
                base_lng,
                radius_km=radius_km,
                dept_keyword=dept_keywords,
                exclude_dept_keywords=_build_exclude_depts(dept_keywords) or None,
                exclude_name_keywords=exclude_name_keywords,
                only_accepting_now=only_accepting_now,
                soon_close_threshold_min=soon_close_threshold_min,
                limit=limit,
            )

            if out is not None and not out.empty:
                out = out.copy()
                out["検索起点"] = origin
                merged_rows.append(out)

        if not merged_rows:
            st.info("近くのクリニックが見つかりませんでした。")
            return

        merged = pd.concat(merged_rows, ignore_index=True)

        sort_cols = []
        if "minutes_to_close" in merged.columns:
            sort_cols.append("minutes_to_close")
        if "distance_km" in merged.columns:
            sort_cols.append("distance_km")
        if sort_cols:
            merged = merged.sort_values(by=sort_cols, ascending=True)

        topn = merged.head(int(limit))
        _render_map_if_possible(topn)

        for i, row in enumerate(topn.to_dict(orient="records"), 1):
            name = _pick_first(row, ["正式名称", "医療機関名称", "医療機関名", "名称", "name"], default="（名称不明）")
            origin = row.get("検索起点", "")
            status = str(row.get("reception_status", "")).strip()

            header = f"**{i}. {name}**"
            if origin:
                header += f"  —  起点: {origin}"
            if status:
                header += f"  —  {status}"

            with st.expander(header, expanded=(i <= 3)):
                # 既存ブロックを再利用
                _render_results_block(
                    origin_label=str(origin),
                    df=df,
                    base_lat=float(row.get("所在地座標（緯度）", current_latlng[0] or 0) or 0),
                    base_lng=float(row.get("所在地座標（経度）", current_latlng[1] or 0) or 0),
                    radius_km=radius_km,
                    dept_keywords=dept_keywords,
                    exclude_name_keywords=exclude_name_keywords,
                    only_accepting_now=only_accepting_now,
                    soon_close_threshold_min=soon_close_threshold_min,
                    limit=1,
                )
                st.caption(f"ID: {row.get('ID','')}")
    else:
        tabs = st.tabs(stations_selected)
        for tab, origin in zip(tabs, stations_selected):
            with tab:
                st.subheader(f"📍 {origin} 周辺")

                if origin == ORIGIN_CURRENT:
                    if current_latlng == (None, None):
                        st.info("現在地を取得できなかったため表示できません。")
                        continue
                    base_lat, base_lng = current_latlng
                else:
                    base_lat, base_lng = STATIONS[origin]

                _render_results_block(
                    origin_label=origin,
                    df=df,
                    base_lat=base_lat,
                    base_lng=base_lng,
                    radius_km=radius_km,
                    dept_keywords=dept_keywords,
                    exclude_name_keywords=exclude_name_keywords,
                    only_accepting_now=only_accepting_now,
                    soon_close_threshold_min=soon_close_threshold_min,
                    limit=limit,
                )

    # ---- PQRST ----
    st.header("5. PQRSTメモ")
    if st.session_state.pqrst_notes:
        st.code(st.session_state.pqrst_notes, language=None)
    else:
        st.info("PQRSTメモを生成できませんでした。")

    if st.button("最初からやり直す"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        _init_state()
        if "step" in st.query_params:
            del st.query_params["step"]
        st.rerun()


def main():
    render_header()

    # セッション切れ時（Cloud Run の再起動などで step だけ URL から復元した場合）
    if st.session_state.get("_session_expired"):
        st.warning(
            "前のセッションが切れました（サーバーが再起動した可能性があります）。"
            " 下のボタンで最初からやり直してください。"
        )
        if st.button("最初からやり直す"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            _init_state()
            st.query_params.clear()
            st.rerun()
        return

    if st.session_state.step == 1:
        render_symptom_input()
    elif st.session_state.step == 2:
        render_additional_questions()
    elif st.session_state.step == 3:
        render_recommendation_and_clinics()


if __name__ == "__main__":
    main()
