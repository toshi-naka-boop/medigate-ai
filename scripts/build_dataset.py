import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_DIR = os.path.join(BASE_DIR, "output")

FACILITY_CSV = os.path.join(DATA_DIR, "facility.csv")      # 施設マスタ
DEPT_CSV = os.path.join(DATA_DIR, "dept_hours.csv")        # 診療科・受付時間
OUT_CSV = os.path.join(OUT_DIR, "clinics_merged.csv")

os.makedirs(OUT_DIR, exist_ok=True)

DAYS = ["月","火","水","木","金","土","日","祝"]

def _min_time(series: pd.Series) -> str:
    vals = []
    for v in series.astype(str).tolist():
        v = v.strip()
        if not v or v.lower() == "nan" or v == "0":
            continue
        vals.append(v)
    return min(vals) if vals else ""

def _max_time(series: pd.Series) -> str:
    vals = []
    for v in series.astype(str).tolist():
        v = v.strip()
        if not v or v.lower() == "nan" or v == "0":
            continue
        vals.append(v)
    return max(vals) if vals else ""

def main():
    # 1) CSVを読む（配布CSVはcp932想定）
    fac = pd.read_csv(FACILITY_CSV, dtype=str, encoding="utf-8-sig")
    dep = pd.read_csv(DEPT_CSV, dtype=str, encoding="utf-8-sig")

    # 2) クリニックのみ（機関区分=2）※データがクリニックのみでも安全のため残す
    fac["機関区分"] = fac["機関区分"].astype(str).str.strip()
    fac = fac[fac["機関区分"] == "2"].copy()

    # 3) 診療科目を施設ごとにまとめる（ユニーク化して連結）
    dep["診療科目名"] = dep["診療科目名"].fillna("").astype(str).str.strip()
    dept_agg = (
        dep.groupby("ID")["診療科目名"]
          .apply(lambda s: " / ".join(sorted(set([x for x in s if x]))))
          .reset_index()
          .rename(columns={"診療科目名": "標ぼう科目_一覧"})
    )

    # 4) 外来受付時間を曜日ごとにまとめる（最小開始～最大終了）
    for d in DAYS:
        start_col = f"{d}_外来受付開始時間"
        end_col   = f"{d}_外来受付終了時間"
        if start_col not in dep.columns:
            dep[start_col] = ""
        if end_col not in dep.columns:
            dep[end_col] = ""
        dep[start_col] = dep[start_col].fillna("").astype(str).str.strip()
        dep[end_col]   = dep[end_col].fillna("").astype(str).str.strip()

    agg_dict = {}
    for d in DAYS:
        agg_dict[f"{d}_外来受付開始時間"] = _min_time
        agg_dict[f"{d}_外来受付終了時間"] = _max_time

    rec_agg = dep.groupby("ID").agg(agg_dict).reset_index()

    # 5) 施設マスタに結合（IDでLEFT JOIN）
    merged = fac.merge(dept_agg, on="ID", how="left").merge(rec_agg, on="ID", how="left")

    # 6) 緯度経度を数値化（後で距離計算用）
    merged["所在地座標（緯度）"] = pd.to_numeric(merged["所在地座標（緯度）"], errors="coerce")
    merged["所在地座標（経度）"] = pd.to_numeric(merged["所在地座標（経度）"], errors="coerce")

    # 7) 保存（utf-8）
    merged.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print("✅ saved:", OUT_CSV)
    print("rows:", len(merged), "cols:", len(merged.columns))

if __name__ == "__main__":
    main()
