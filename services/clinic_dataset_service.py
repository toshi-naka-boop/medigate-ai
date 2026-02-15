# -*- coding: utf-8 -*-
"""
clinic_dataset_service.py
- クリニックCSVを読み込み、起点(lat,lng)から近い順に検索
- 受付中/もうすぐ終了/受付外/不明 のステータス付与
- 次回受付開始ラベル(next_reception_label) を付与
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union, List

import pandas as pd
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")

# CSVの想定パス（プロジェクトルート/output/clinics_merged.csv）
DEFAULT_CSV_PATH = Path(__file__).resolve().parents[1] / "output" / "clinics_merged.csv"

# 月(0)〜日(6) で使う曜日プレフィックス（CSV列の先頭）
WEEKDAY_PREFIX = {
    0: "月",
    1: "火",
    2: "水",
    3: "木",
    4: "金",
    5: "土",
    6: "日",
}

START_SUFFIX = "_外来受付開始時間"
END_SUFFIX = "_外来受付終了時間"


# -------------------------
# Dataset load
# -------------------------
def load_clinic_dataset(csv_path: Union[str, Path] = DEFAULT_CSV_PATH) -> pd.DataFrame:
    """
    clinics_merged.csv を読み込む。
    文字コードは utf-8-sig を第一候補、失敗時は cp932 にフォールバック。
    """
    p = Path(csv_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {p}")

    # まず utf-8-sig（BOMありUTF-8）を試す
    try:
        df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        return df
    except Exception:
        pass

    # 次に Windows系の cp932 を試す
    df = pd.read_csv(p, encoding="cp932", low_memory=False)
    return df


# -------------------------
# Distance
# -------------------------
def _haversine_km(lat1: float, lng1: float, lat2: pd.Series, lng2: pd.Series) -> pd.Series:
    """
    起点(lat1,lng1) と Series(lat2,lng2) の距離(km)を返す（ベクトル化）
    """
    r = 6371.0
    phi1 = math.radians(lat1)
    lam1 = math.radians(lng1)

    phi2 = lat2.astype(float).map(math.radians)
    lam2 = lng2.astype(float).map(math.radians)

    dphi = phi2 - phi1
    dlam = lam2 - lam1

    a = (dphi / 2).map(math.sin).pow(2) + phi2.map(math.cos) * math.cos(phi1) * (dlam / 2).map(math.sin).pow(2)
    c = a.map(math.sqrt).map(lambda x: 2 * math.asin(min(1.0, x)))
    return c * r


# -------------------------
# Time parsing & status
# -------------------------
def _parse_hhmm(x) -> Optional[time]:
    """
    '09:30', '930', '0930', 930 などを time(9,30) に変換。
    """
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None

    s = str(x).strip()
    if not s:
        return None

    # "9:30"
    if ":" in s:
        parts = s.split(":")
        if len(parts) >= 2:
            try:
                hh = int(parts[0])
                mm = int(parts[1])
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    return time(hh, mm)
            except Exception:
                return None

    # "930" / "0930"
    # 数字以外除去
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 3:
        digits = "0" + digits
    if len(digits) == 4:
        try:
            hh = int(digits[:2])
            mm = int(digits[2:])
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return time(hh, mm)
        except Exception:
            return None

    return None


def _today_cols(now: datetime) -> tuple[str, str]:
    prefix = WEEKDAY_PREFIX.get(now.weekday(), "月")
    return f"{prefix}{START_SUFFIX}", f"{prefix}{END_SUFFIX}"


def _make_dt(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=JST)


def _minutes_to_close(row: pd.Series, now: datetime) -> Optional[int]:
    """
    今日の受付時間内なら終了までの残分を返す。受付時間外/不明なら None。
    """
    start_col, end_col = _today_cols(now)
    if start_col not in row or end_col not in row:
        return None

    st_t = _parse_hhmm(row.get(start_col))
    ed_t = _parse_hhmm(row.get(end_col))
    if not st_t or not ed_t:
        return None

    start_dt = _make_dt(now.date(), st_t)
    end_dt = _make_dt(now.date(), ed_t)

    # もし終了が開始より早い（深夜跨ぎ）なら翌日に
    if end_dt <= start_dt:
        end_dt = end_dt + timedelta(days=1)

    if start_dt <= now <= end_dt:
        mins = int((end_dt - now).total_seconds() // 60)
        return max(mins, 0)

    return None


def _status_label(minutes_to_close: Optional[int], soon_close_threshold_min: int) -> str:
    """
    minutes_to_close が None: 不明/受付外（ここでは一旦不明寄り）
    """
    if minutes_to_close is None:
        return "受付時間不明/受付外"
    if minutes_to_close <= soon_close_threshold_min:
        return "🟠 もうすぐ受付終了"
    return "🟢 受付中"


def _next_reception_start(row: pd.Series, now: datetime) -> Optional[datetime]:
    """
    次に受付開始する日時を推定して返す（最大7日先まで）。
    今日がまだ開始前なら今日の開始。
    """
    base_date = now.date()

    for offset in range(0, 7):
        d = base_date + timedelta(days=offset)
        wd = (now.weekday() + offset) % 7
        prefix = WEEKDAY_PREFIX.get(wd, "月")

        start_col = f"{prefix}{START_SUFFIX}"
        end_col = f"{prefix}{END_SUFFIX}"

        if start_col not in row or end_col not in row:
            continue

        st_t = _parse_hhmm(row.get(start_col))
        ed_t = _parse_hhmm(row.get(end_col))
        if not st_t or not ed_t:
            continue

        start_dt = _make_dt(d, st_t)
        end_dt = _make_dt(d, ed_t)
        if end_dt <= start_dt:
            end_dt = end_dt + timedelta(days=1)

        if offset == 0:
            # 今日：開始前なら start、受付中なら次回は不要(None)、終了後なら次の日へ
            if now < start_dt:
                return start_dt
            if start_dt <= now <= end_dt:
                return None
            # 終了後は次の候補へ
        else:
            return start_dt

    return None


def _weekday_jp(dt: datetime) -> str:
    # dt.weekday(): Monday=0
    return WEEKDAY_PREFIX.get(dt.weekday(), "")


def _next_start_label(
    next_start: Optional[datetime],
    now: datetime,
    soon_start_threshold_min: int = 15,
) -> str:
    """
    次回受付開始のラベルを作る。
    soon_start_threshold_min 分以内なら「まもなく」を付ける。
    """
    if next_start is None or pd.isna(next_start):
        return ""

    delta_min = int((next_start - now).total_seconds() // 60)
    hhmm = next_start.strftime("%H:%M")

    if next_start.date() == now.date():
        day = "本日"
    elif next_start.date() == (now.date() + timedelta(days=1)):
        day = "明日"
    else:
        day = f"{_weekday_jp(next_start)}曜日"

    prefix = "まもなく " if 0 <= delta_min <= soon_start_threshold_min else ""
    return f"{prefix}{day} {hhmm}〜"


# -------------------------
# Search main
# -------------------------
def _to_list(x) -> List[str]:
    if x is None:
        return []
    if isinstance(x, str):
        return [x]
    return [str(v) for v in x]


def search_clinics_near_point(
    df: pd.DataFrame,
    base_lat: float,
    base_lng: float,
    *,
    radius_km: float = 2.0,
    dept_keyword: Optional[Union[str, Sequence[str]]] = None,
    exclude_dept_keywords: Optional[Sequence[str]] = None,
    exclude_name_keywords: Optional[Sequence[str]] = None,
    only_accepting_now: bool = False,
    soon_close_threshold_min: int = 30,
    soon_start_threshold_min: int = 15,
    limit: int = 10,
) -> pd.DataFrame:
    """
    近隣クリニック検索の主処理。

    - 起点(base_lat, base_lng)から距離計算し radius_km 以内に絞る
    - 標ぼう科目_一覧 で include/exclude
    - 名称キーワードで除外
    - 受付状況(reception_status)、minutes_to_close、next_reception_label を付与
    - only_accepting_now=True の場合は受付中のみ残す
    - ソート：推奨診療科一致優先（第一推奨科マッチを最前）→ minutes_to_close → distance_km
    """
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()

    # 緯度経度列
    lat_col = "所在地座標（緯度）"
    lng_col = "所在地座標（経度）"
    if lat_col not in work.columns or lng_col not in work.columns:
        # 他の列名でも来る可能性はあるが、MVPでは固定で
        raise KeyError(f"Missing lat/lng columns: {lat_col}, {lng_col}")

    # numeric化 & 欠損除外
    work[lat_col] = pd.to_numeric(work[lat_col], errors="coerce")
    work[lng_col] = pd.to_numeric(work[lng_col], errors="coerce")
    work = work.dropna(subset=[lat_col, lng_col])

    # 距離計算 & 半径フィルタ
    work["distance_km"] = _haversine_km(base_lat, base_lng, work[lat_col], work[lng_col])
    work = work[work["distance_km"] <= float(radius_km)].copy()

    if work.empty:
        return work

    # フィルタ用 series（※必ず work の index に追従させる）
    name_series = None
    dept_series = None

    # 名称（候補列）
    name_cols = [c for c in ["医療機関名称", "医療機関名", "名称", "name"] if c in work.columns]
    if name_cols:
        name_series = work[name_cols[0]].astype(str)
    else:
        name_series = pd.Series([""] * len(work), index=work.index)

    # 標ぼう科目
    dept_col = "標ぼう科目_一覧" if "標ぼう科目_一覧" in work.columns else None
    if dept_col:
        dept_series = work[dept_col].astype(str)
    else:
        dept_series = pd.Series([""] * len(work), index=work.index)

    # include: 診療科キーワード
    dept_keywords = _to_list(dept_keyword)
    if dept_keywords:
        pat = "|".join(map(lambda s: str(s), dept_keywords))
        mask = dept_series.str.contains(pat, na=False)
        work = work[mask].copy()
        # 追従更新（reindex warning避け）
        name_series = name_series.loc[work.index]
        dept_series = dept_series.loc[work.index]

    # exclude: 診療科除外
    if exclude_dept_keywords:
        pat = "|".join(map(lambda s: str(s), exclude_dept_keywords))
        mask = dept_series.str.contains(pat, na=False)
        work = work[~mask].copy()
        name_series = name_series.loc[work.index]
        dept_series = dept_series.loc[work.index]

    # exclude: 名称除外
    if exclude_name_keywords:
        pat = "|".join(map(lambda s: str(s), exclude_name_keywords))
        mask = name_series.str.contains(pat, na=False)
        work = work[~mask].copy()
        name_series = name_series.loc[work.index]
        dept_series = dept_series.loc[work.index]

    if work.empty:
        return work

    # 受付状況
    now = datetime.now(tz=JST)
    work["minutes_to_close"] = work.apply(lambda r: _minutes_to_close(r, now), axis=1)
    work["reception_status"] = work["minutes_to_close"].apply(
        lambda m: _status_label(m, int(soon_close_threshold_min))
    )

    # 次回受付開始
    work["next_reception_start"] = work.apply(lambda r: _next_reception_start(r, now), axis=1)
    work["next_reception_label"] = work["next_reception_start"].apply(
        lambda x: _next_start_label(x, now, soon_start_threshold_min=int(soon_start_threshold_min))
    )

    # 受付中のみ
    if only_accepting_now:
        work = work[work["minutes_to_close"].notna()].copy()

    # 推奨診療科の一致優先度（第一推奨科マッチ=0, 第二=1, ... マッチなし=999）
    dept_keywords_ordered = _to_list(dept_keyword)
    if dept_keywords_ordered:
        def _row_dept_priority(row: pd.Series) -> int:
            s = dept_series.get(row.name, "") or ""
            for i, kw in enumerate(dept_keywords_ordered):
                if kw and str(kw) in s:
                    return i
            return 999

        work["_sort_dept_priority"] = work.apply(_row_dept_priority, axis=1)
    else:
        work["_sort_dept_priority"] = 0

    # ソート：推奨科一致優先 → 受付終了までの分 → 距離
    work["_sort_mins"] = work["minutes_to_close"].fillna(10**9).astype(int)
    work = work.sort_values(
        by=["_sort_dept_priority", "_sort_mins", "distance_km"],
        ascending=[True, True, True],
    ).drop(columns=["_sort_dept_priority", "_sort_mins"])

    if limit and int(limit) > 0:
        work = work.head(int(limit)).copy()

    return work
