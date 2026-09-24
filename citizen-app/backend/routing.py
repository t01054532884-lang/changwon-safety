"""창원 안심길 — Stage 3: 안심경로(최단/균형/안심우선) 라우팅 엔진.

⚠️ 알려진 한계 (README에도 명시):
이 샌드박스 환경은 OSM/네이버/카카오 등 외부 지도·routing API에 네트워크로
접근할 수 없어(egress 정책상 pypi/npm 등만 허용) 실제 도로망 좌표를 받아올 수
없다. 그래서 실제 도로를 따라가는 turn-by-turn 경로 대신, 출발지~도착지 주변에
격자(그리드) 그래프를 만들고 그 위에서 다익스트라 최단경로를 계산하는 방식으로
'거리 vs 안전도'를 트레이드오프하는 3가지 경로를 만든다.

격자의 각 노드에는 우리가 이미 갖고 있는 실측 데이터 기반 위험도를 매긴다:
- scoring.protection_score_at(): CCTV/보안등/공공Wi-Fi/파출소 실측 좌표 기반 접근성
- scoring.nearest_top10(): 노트북에서 산출된 연령대별(어린이/노인) TOP10 취약지역 실좌표 근접도

즉 "안심 우선" 경로가 실제로 우회하는 지점들은 임의 값이 아니라 이 두 실데이터로
계산된 위험도가 높은 지점들이다. 다만 경로 자체의 기하(도로를 따라가는지 여부)는
근사치이므로, 실서비스 전환 시 네이버/카카오 Directions API 연동으로 교체가 필요하다.
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from scoring import haversine_m, risk_at

GRID_N = 27  # 축당 노드 수 (총 GRID_N^2개, 거리와 무관하게 계산량을 일정하게 유지)
PAD_FRAC = 0.35  # 시작~끝 직선 bbox 대비 여유 폭 비율 (우회 공간 확보)
PAD_MIN_M = 120.0
MAX_STRAIGHT_M = 60_000.0  # 60km 초과 요청은 프로토타입 범위 밖으로 거절

WALK_SPEED_M_PER_MIN = 80.0  # 도보 약 4.8km/h 가정

VARIANTS = {
    "fast": {"label": "최단", "risk_weight": 0.0},
    "balanced": {"label": "균형", "risk_weight": 1.4},
    "safe": {"label": "안심 우선", "risk_weight": 4.5},
}


class RouteError(Exception):
    pass


def _meters_per_degree(lat_deg: float) -> tuple[float, float]:
    lat_rad = math.radians(lat_deg)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(lat_rad)
    return m_per_deg_lat, max(1.0, m_per_deg_lon)


def _build_grid(start_lat, start_lng, end_lat, end_lng):
    mid_lat = (start_lat + end_lat) / 2.0
    m_per_lat, m_per_lon = _meters_per_degree(mid_lat)

    lat_min, lat_max = sorted([start_lat, end_lat])
    lon_min, lon_max = sorted([start_lng, end_lng])

    straight_m = haversine_m(start_lat, start_lng, end_lat, end_lng)
    pad_m = max(PAD_MIN_M, straight_m * PAD_FRAC)

    lat_min -= pad_m / m_per_lat
    lat_max += pad_m / m_per_lat
    lon_min -= pad_m / m_per_lon
    lon_max += pad_m / m_per_lon

    lat_vals = np.linspace(lat_min, lat_max, GRID_N)
    lon_vals = np.linspace(lon_min, lon_max, GRID_N)
    return lat_vals, lon_vals


def _nearest_index(vals: np.ndarray, target: float) -> int:
    return int(np.abs(vals - target).argmin())


def compute_routes(start_lat, start_lng, end_lat, end_lng, age_group: str) -> dict:
    straight_m = haversine_m(start_lat, start_lng, end_lat, end_lng)
    if straight_m > MAX_STRAIGHT_M:
        raise RouteError(f"출발지-도착지 직선거리({straight_m/1000:.1f}km)가 프로토타입 지원 범위를 벗어났습니다.")
    if straight_m < 5:
        raise RouteError("출발지와 도착지가 너무 가깝습니다.")

    lat_vals, lon_vals = _build_grid(start_lat, start_lng, end_lat, end_lng)
    n = GRID_N

    # 노드별 위험도(0~1) 계산 — 실측 데이터 기반 scoring.risk_at() 재사용
    risk_grid = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            risk_grid[i, j] = risk_at(float(lat_vals[i]), float(lon_vals[j]), age_group)

    def node_id(i, j):
        return i * n + j

    def node_latlon(i, j):
        return float(lat_vals[i]), float(lon_vals[j])

    # 8방향 인접 그래프의 간선 목록 (노드쌍, 실거리) — 위험도 가중은 변형별로 나중에 곱한다
    neighbor_offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    edges = []  # (i,j,ni,nj,dist_m)
    for i in range(n):
        for j in range(n):
            lat1, lon1 = node_latlon(i, j)
            for di, dj in neighbor_offsets:
                ni, nj = i + di, j + dj
                if 0 <= ni < n and 0 <= nj < n:
                    if di in (1,) or (di == 0 and dj == 1):  # 각 무방향 간선을 한 번씩만 저장
                        lat2, lon2 = node_latlon(ni, nj)
                        dist = haversine_m(lat1, lon1, lat2, lon2)
                        edges.append((i, j, ni, nj, dist))

    start_i, start_j = _nearest_index(lat_vals, start_lat), _nearest_index(lon_vals, start_lng)
    end_i, end_j = _nearest_index(lat_vals, end_lat), _nearest_index(lon_vals, end_lng)
    start_node = node_id(start_i, start_j)
    end_node = node_id(end_i, end_j)

    def dijkstra(risk_weight: float):
        adj = {}
        for i, j, ni, nj, dist in edges:
            a, b = node_id(i, j), node_id(ni, nj)
            avg_risk = (risk_grid[i, j] + risk_grid[ni, nj]) / 2.0
            cost = dist * (1.0 + risk_weight * avg_risk)
            adj.setdefault(a, []).append((b, cost, dist))
            adj.setdefault(b, []).append((a, cost, dist))

        dist_to = {start_node: 0.0}
        prev = {}
        visited = set()
        pq = [(0.0, start_node)]
        while pq:
            d, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)
            if u == end_node:
                break
            for v, cost, _raw in adj.get(u, []):
                nd = d + cost
                if nd < dist_to.get(v, math.inf):
                    dist_to[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))

        if end_node not in dist_to:
            return None

        path_nodes = [end_node]
        while path_nodes[-1] != start_node:
            path_nodes.append(prev[path_nodes[-1]])
        path_nodes.reverse()

        raw_dist_map = {}
        for i, j, ni, nj, dist in edges:
            a, b = node_id(i, j), node_id(ni, nj)
            raw_dist_map[(a, b)] = dist
            raw_dist_map[(b, a)] = dist

        total_m = 0.0
        risks = []
        latlon_path = [(start_lat, start_lng)]
        for k in range(len(path_nodes) - 1):
            a, b = path_nodes[k], path_nodes[k + 1]
            total_m += raw_dist_map[(a, b)]
        for node in path_nodes:
            i, j = divmod(node, n)
            latlon_path.append(node_latlon(i, j))
            risks.append(risk_grid[i, j])
        latlon_path.append((end_lat, end_lng))

        avg_risk = float(np.mean(risks)) if risks else 0.0
        return {
            "distance_m": round(total_m, 1),
            "avg_risk": round(avg_risk, 3),
            "path": [{"lat": round(la, 6), "lng": round(lo, 6)} for la, lo in latlon_path],
        }

    def safety_label(avg_risk: float) -> str:
        score = 100.0 * (1.0 - avg_risk)
        if score >= 75:
            return "매우안전"
        if score >= 55:
            return "안전"
        if score >= 35:
            return "보통"
        if score >= 20:
            return "위험"
        return "매우위험"

    results = {}
    for key, spec in VARIANTS.items():
        r = dijkstra(spec["risk_weight"])
        if r is None:
            continue
        r["type"] = key
        r["label"] = spec["label"]
        r["duration_min"] = max(1, round(r["distance_m"] / WALK_SPEED_M_PER_MIN))
        r["safety_label"] = safety_label(r["avg_risk"])
        results[key] = r

    if not results:
        raise RouteError("경로를 찾지 못했습니다. 다른 도착지를 선택해주세요.")

    return {
        "start": {"lat": start_lat, "lng": start_lng},
        "end": {"lat": end_lat, "lng": end_lng},
        "age_group": age_group,
        "straight_distance_m": round(straight_m, 1),
        "routes": results,
        "note": (
            "실제 도로망 API(네이버/카카오/OSRM) 없이, 실측 CCTV·보안등·Wi-Fi·파출소 접근성과 "
            "연령대별 TOP10 취약지역 근접도로 위험도를 매긴 격자 위에서 계산한 근사 경로입니다."
        ),
    }
