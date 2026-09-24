"""창원 안심길 백엔드 — 공용 안전도 계산 로직.

main.py(/api/safety)와 routing.py(/api/route)가 동일한 기준으로 안전도를
계산하도록 로직을 이 모듈 하나로 모았다. (저장소 analysis/vulnerability.py의
CCTV/보안등/공공Wi-Fi/파출소 접근성 공식을 그대로 재사용)
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

import data_loader as dl

# ---------- 저장소 실데이터 로드 (모듈 최초 import 시 1회) ----------
FACILITIES = {
    "cctv": {"coords": dl.load_cctv(), "radius_m": 100.0, "weight": 0.40},
    "light": {"coords": dl.load_lights(), "radius_m": 50.0, "weight": 0.35},
    "wifi": {"coords": dl.load_wifi(), "radius_m": 100.0, "weight": 0.10},
    "police": {"coords": dl.load_police(), "radius_m": 1_000.0, "weight": 0.15},
}
TOP10_ZONES = {
    "child": dl.load_top10("child_top10"),
    "senior": dl.load_top10("elderly_top10"),
}
BOUNDARY = dl.load_boundary()

# Stage 7: Colab 노트북(OOEZ.ipynb)이 어린이/노인 생활권 격자 전체(각 8,670개/18,708개)에
# CRITIC 가중치로 산출한 최종 vulnerability_score. TOP10_ZONES(대표 10곳만)보다 훨씬
# 촘촘한 실데이터라, risk_at()에서 기존 TOP10 근접 보정 대신 이걸 직접 사용한다.
VULN_GRID = {
    "child": dl.load_vulnerability_grid("child"),
    "senior": dl.load_vulnerability_grid("elderly"),
}


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_vec(lat, lon, coords: np.ndarray) -> np.ndarray:
    if coords.size == 0:
        return np.array([])
    r = 6_371_000
    p1 = math.radians(lat)
    p2 = np.radians(coords[:, 0])
    dphi = np.radians(coords[:, 0] - lat)
    dlambda = np.radians(coords[:, 1] - lon)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def point_in_polygon(lat, lon, geometry) -> bool:
    def in_ring(x, y, ring):
        inside = False
        x1, y1 = ring[-1][0], ring[-1][1]
        for x2, y2 in ring:
            if (y1 > y) != (y2 > y):
                xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < xin:
                    inside = not inside
            x1, y1 = x2, y2
        return inside

    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for poly in polys:
        if in_ring(lon, lat, poly[0]):
            if any(in_ring(lon, lat, hole) for hole in poly[1:]):
                continue
            return True
    return False


@lru_cache(maxsize=1)
def reference_densities() -> dict:
    """도시 내 무작위 표본점으로 시설별 '기준 밀도'(75분위수)를 1회 산출해 캐시."""
    coords = np.array(BOUNDARY["features"][0]["geometry"]["coordinates"][0])
    lon_min, lon_max = coords[:, 0].min(), coords[:, 0].max()
    lat_min, lat_max = coords[:, 1].min(), coords[:, 1].max()

    rng = np.random.default_rng(42)
    samples = []
    while len(samples) < 1500:
        lat = rng.uniform(lat_min, lat_max)
        lon = rng.uniform(lon_min, lon_max)
        if point_in_polygon(lat, lon, BOUNDARY["features"][0]["geometry"]):
            samples.append((lat, lon))
    samples = np.array(samples)

    refs = {}
    for key, spec in FACILITIES.items():
        counts = np.array([
            int((haversine_vec(lat, lon, spec["coords"]) <= spec["radius_m"]).sum())
            for lat, lon in samples
        ])
        positive = counts[counts > 0]
        refs[key] = max(1.0, float(np.quantile(positive, 0.75))) if len(positive) else 1.0
    return refs


def facility_score(lat, lon, key) -> dict:
    spec = FACILITIES[key]
    dists = haversine_vec(lat, lon, spec["coords"])
    if dists.size == 0:
        return {"distance_m": None, "count": 0, "score": None}
    nearest = float(dists.min())
    count = int((dists <= spec["radius_m"]).sum())
    ref = reference_densities()[key]
    distance_score = max(0.0, 1.0 - nearest / spec["radius_m"])
    density_score = 1.0 - math.exp(-count / ref)
    score = 100.0 * (0.6 * distance_score + 0.4 * density_score)
    return {"distance_m": round(nearest, 1), "count": count, "score": round(score, 1)}


def protection_score_at(lat, lon) -> float:
    """CCTV/보안등/Wi-Fi/파출소 접근성을 가중합한 0~100 보호점수만 반환."""
    scores = {key: facility_score(lat, lon, key) for key in FACILITIES}
    available = [(FACILITIES[k]["weight"], v["score"]) for k, v in scores.items() if v["score"] is not None]
    total_w = sum(w for w, _ in available) or 1.0
    return sum(w * s for w, s in available) / total_w


def nearest_top10(lat, lon, age_group: str):
    if age_group == "child":
        pools = [("child", TOP10_ZONES["child"])]
    elif age_group == "senior":
        pools = [("senior", TOP10_ZONES["senior"])]
    else:
        pools = [("child", TOP10_ZONES["child"]), ("senior", TOP10_ZONES["senior"])]

    best = None
    for kind, zones in pools:
        for z in zones:
            d = haversine_m(lat, lon, z["lat"], z["lon"])
            if best is None or d < best["distance_m"]:
                best = {"kind": kind, "distance_m": round(d, 1), **z}
    return best


def _grid_vuln_pools(age_group: str) -> list[np.ndarray]:
    if age_group == "child":
        return [VULN_GRID["child"]]
    if age_group == "senior":
        return [VULN_GRID["senior"]]
    return [VULN_GRID["child"], VULN_GRID["senior"]]  # adult: 둘 다 참고(더 위험한 쪽 채택)


def grid_vulnerability_at(lat, lon, age_group: str) -> float:
    """가장 가까운 Colab 최종 취약도 격자의 vulnerability_score를 거리 감쇠와 함께 반환.

    격자 간격이 약 100m라 정확히 그 지점이 아니어도 바로 옆 도로를 지나갈 수 있으므로,
    가장 가까운 격자까지의 거리에 따라 그 격자 값을 얼마나 반영할지 감쇠시킨다
    (nearest_top10의 거리별 보정과 같은 방식 — 이 코드베이스의 기존 관례를 따름).
    """
    best = 0.0
    for pool in _grid_vuln_pools(age_group):
        if pool.size == 0:
            continue
        dists = haversine_vec(lat, lon, pool[:, :2])
        idx = int(np.argmin(dists))
        d = float(dists[idx])
        score = float(pool[idx, 2])
        if d <= 60:
            decay = 1.0
        elif d <= 150:
            decay = 0.6
        elif d <= 300:
            decay = 0.3
        else:
            decay = 0.0
        best = max(best, score * decay)
    return best


def grade_from_score(protection_score: float, hotspot: dict | None) -> tuple[int, int]:
    """(infra_grade, grade) 계산 — /api/safety와 동일한 등급 규칙."""
    if protection_score >= 75:
        infra_grade = 5
    elif protection_score >= 55:
        infra_grade = 4
    elif protection_score >= 35:
        infra_grade = 3
    elif protection_score >= 20:
        infra_grade = 2
    else:
        infra_grade = 1

    grade = infra_grade
    if hotspot:
        if hotspot["distance_m"] <= 150:
            grade = min(grade, 1)
        elif hotspot["distance_m"] <= 400:
            grade = min(grade, 2)
        elif hotspot["distance_m"] <= 800:
            grade = min(grade, 3)
    return infra_grade, grade


def risk_at(lat, lon, age_group: str) -> float:
    """경로 가중치용 0~1 위험도 (안전할수록 0에 가까움).

    - 0.50: 보호점수(실측 CCTV/보안등/Wi-Fi/파출소 접근성) 기반 위험도 — 도시 전역에
      고르게 존재하는 신호.
    - 0.35: (Stage 7, 2026-09-25 추가) Colab 노트북(OOEZ.ipynb STEP0~6)이 어린이/노인
      생활권 격자 전체(각 8,670개/18,708개, TOP10보다 훨씬 촘촘함)에 CRITIC 가중치로
      산출한 실제 vulnerability_score. 예전에는 이 분석 결과가 대표 10곳(TOP10)을 통해서만
      간접적으로 반영됐는데, 이제 격자 값을 직접 조회해서 훨씬 세밀하게 반영한다.
    - 0.15: 연령대별 TOP10 취약지역 근접 보정 — 이 프로젝트가 공식적으로 선정한 "가장
      심각한 10곳"이라는 추가적 의미가 있어 작은 가중치로 남겨둔다(위 vulnerability_score와
      상당 부분 겹치는 신호이므로 비중은 낮춤).
    셋 다 실측/실분석 데이터 기반이며, 임의로 지어낸 값이 아니다.
    """
    protection = protection_score_at(lat, lon)
    base_risk = max(0.0, min(1.0, 1.0 - protection / 100.0))

    grid_vuln = grid_vulnerability_at(lat, lon, age_group)

    hotspot = nearest_top10(lat, lon, age_group)
    zone_risk = 0.0
    if hotspot:
        d = hotspot["distance_m"]
        if d <= 150:
            zone_risk = 1.0
        elif d <= 400:
            zone_risk = 0.6
        elif d <= 800:
            zone_risk = 0.3

    return max(0.0, min(1.0, 0.50 * base_risk + 0.35 * grid_vuln + 0.15 * zone_risk))
