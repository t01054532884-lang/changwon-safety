"""창원 안심길 백엔드 — 저장소(changwon-safety) 원본 데이터 로더.

주의: 여기서는 '실제로 확보된 데이터'만 사용한다.
- CCTV/보안등/공공Wi-Fi/파출소 좌표: data/*.csv, *.xlsx, *.json (실측 데이터)
- 어린이/노인 최종 취약지역 TOP10: data/*_top10.geojson (Colab 노트북 산출 실데이터)
생활안전지도 WMS 기반 '범죄 고위험 적색영역'은 API KEY가 없어 임의 좌표에 대해
실시간으로 재현할 수 없으므로, TOP10 좌표 근접 여부로만 참고 반영한다.
(→ 도시 전역 실제 범죄위험 격자를 쓰려면 생활안전지도 API KEY 연동이 추가로 필요함)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _resolve_repo_root() -> Path:
    """저장소 루트 경로를 찾는다.

    우선순위: 1) ANSHIMGIL_REPO_ROOT 환경변수(배포 환경에서 명시 지정용)
              2) 이 파일 기준 상대경로 — 배포 시 구조: changwon-safety/citizen-app/backend/data_loader.py
                 → 저장소 루트는 parent.parent.parent
              3) (2)에 data/ 폴더가 없으면) 개발 샌드박스에서 쓰던 절대경로 폴백
    """
    env_path = os.environ.get("ANSHIMGIL_REPO_ROOT")
    if env_path:
        return Path(env_path)

    candidate = Path(__file__).resolve().parent.parent.parent
    if (candidate / "data").is_dir():
        return candidate

    return Path("/home/claude/changwon-safety-repo")


REPO_ROOT = _resolve_repo_root()
REPO_DATA = REPO_ROOT / "data"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _to_latlon_array(lats, lons) -> np.ndarray:
    arr = np.column_stack([np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)])
    arr = arr[~np.isnan(arr).any(axis=1)]
    return arr


def load_cctv() -> np.ndarray:
    df = pd.read_excel(REPO_DATA / "cctv_coordinates.xlsx")
    return _to_latlon_array(df["WGS84위도"], df["WGS84경도"])


def load_lights() -> np.ndarray:
    data = json.loads((REPO_DATA / "nonroad_lights.json").read_text(encoding="utf-8"))
    records = data["records"]
    lats = [r["latitude"] for r in records]
    lons = [r["longitude"] for r in records]
    return _to_latlon_array(lats, lons)


def load_wifi() -> np.ndarray:
    df = pd.read_csv(REPO_DATA / "wifi_data.csv", encoding="cp949")
    return _to_latlon_array(df["WGS84위도"], df["WGS84경도"])


def load_police() -> np.ndarray:
    df = pd.read_csv(REPO_DATA / "police_stations.csv", encoding="utf-8-sig")
    return _to_latlon_array(df["위도"], df["경도"])


def load_top10(kind: str) -> list[dict]:
    """kind: 'child_top10' | 'elderly_top10' | 'all_top10'"""
    geojson = json.loads((REPO_DATA / f"{kind}.geojson").read_text(encoding="utf-8"))
    zones = []
    for feature in geojson["features"]:
        p = feature["properties"]
        if p.get("latitude") is None or p.get("longitude") is None:
            continue
        zones.append({
            "label": p.get("top10_label"),
            "lat": float(p["latitude"]),
            "lon": float(p["longitude"]),
            "risk_pct_mean": p.get("risk_pct_mean"),
            "primary_facility": p.get("primary_facility"),
            "facility_priority_order": p.get("facility_priority_order"),
        })
    return zones


def load_boundary() -> dict:
    return json.loads((REPO_DATA / "changwon_boundary.geojson").read_text(encoding="utf-8"))
