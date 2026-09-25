"""창원 안심길 — Stage 3(+Tmap 연동): 안심경로(최단/안심우선) 라우팅 엔진.
 
우선순위:
1. TMAP_APP_KEY가 설정돼 있으면 Tmap(SK Open API) 보행자 경로 API로 "최단" 경로를
   실제 도로(보도)를 따라 받아오고, 실측 위험도가 낮은 지점들을 경유지로 넣어 다시
   Tmap을 호출해가며 "안심 우선" 경로 후보를 탐색한다 (_tmap_compute_routes).
2. Tmap 호출이 실패하면(키 없음/네트워크 오류/응답 이상) 아래 격자 기반 다익스트라
   방식으로 자동 폴백한다(_compute_routes_grid) — 이 샌드박스 개발 환경은 애초에
   Tmap 서버에 네트워크로 접근할 수 없어서 만든 임시 방식이었고, 배포 환경에서
   Tmap 키가 정상 동작하는 한 이 폴백은 거의 쓰이지 않아야 정상이다.
 
격자 폴백 방식의 각 노드에는 우리가 이미 갖고 있는 실측 데이터 기반 위험도를 매긴다:
- scoring.protection_score_at(): CCTV/보안등/공공Wi-Fi/파출소 실측 좌표 기반 접근성
- scoring.nearest_top10(): 노트북에서 산출된 연령대별(어린이/노인) TOP10 취약지역 실좌표 근접도
 
Tmap 방식에서도 경유지 후보를 고를 때 동일한 risk_at()을 사용하므로, "안심 우선"
경로가 우회하는 지점들은 두 방식 모두 임의 값이 아니라 실데이터 기반 위험도가
높은 지점들이다.
"""
from __future__ import annotations
 
import heapq
import math
 
import numpy as np
 
import tmap_client
from scoring import haversine_m, risk_at
 
GRID_N = 27  # 축당 노드 수 (총 GRID_N^2개, 거리와 무관하게 계산량을 일정하게 유지)
PAD_FRAC = 0.35  # 시작~끝 직선 bbox 대비 여유 폭 비율 (우회 공간 확보)
PAD_MIN_M = 120.0
MAX_STRAIGHT_M = 60_000.0  # 60km 초과 요청은 프로토타입 범위 밖으로 거절
 
WALK_SPEED_M_PER_MIN = 80.0  # 도보 약 4.8km/h 가정
 
VARIANTS = {
    "fast": {"label": "최단", "risk_weight": 0.0},
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
 
 
def _compute_routes_grid(start_lat, start_lng, end_lat, end_lng, age_group: str) -> dict:
    """Tmap을 쓸 수 없을 때의 격자 기반 폴백 (Stage 3 원안)."""
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
        "engine": "grid_fallback",
        "note": (
            "Tmap 보행자 API를 사용할 수 없어(키 미설정 또는 호출 실패), 실측 CCTV·보안등·Wi-Fi·파출소 "
            "접근성과 연령대별 TOP10 취약지역 근접도로 위험도를 매긴 격자 위에서 계산한 근사 경로입니다. "
            "실제 도로 형상과 다를 수 있습니다."
        ),
    }
 
 
# ---------------------------------------------------------------------------
# Tmap 보행자 경로 API 연동 (실제 도로/보도 형상)
# ---------------------------------------------------------------------------
 
CANDIDATE_GRID_N = 11  # 경유지 후보 탐색용 (전체 라우팅 격자보다 훨씬 성기게)
MAX_CANDIDATES = 5  # Tmap 호출 횟수를 제한하기 위한 후보 개수 상한
RISK_SAMPLE_STRIDE = 3  # Tmap 경로 좌표 중 매 N번째 점만 위험도 샘플링(호출 비용 절감)
 
 
def _sample_path_risk(path: list[tuple[float, float]], age_group: str) -> float:
    if not path:
        return 0.0
    sampled = path[::RISK_SAMPLE_STRIDE] or path
    risks = [risk_at(lat, lng, age_group) for lat, lng in sampled]
    return float(np.mean(risks)) if risks else 0.0
 
 
def _candidate_waypoints(start_lat, start_lng, end_lat, end_lng, age_group: str) -> list[tuple[float, float]]:
    """출발~도착 사이 padded bbox 안에서 위험도가 낮은 지점들을 경유지 후보로 뽑는다.
    (기존 격자 폴백과 동일한 실측 위험도 기준 risk_at()을 재사용)"""
    lat_vals, lon_vals = _build_grid(start_lat, start_lng, end_lat, end_lng)
    # 성긴 후보 격자로 다시 샘플링 (CANDIDATE_GRID_N개 지점)
    idxs = np.linspace(0, len(lat_vals) - 1, CANDIDATE_GRID_N).round().astype(int)
    cand_lats = lat_vals[idxs]
    idxs2 = np.linspace(0, len(lon_vals) - 1, CANDIDATE_GRID_N).round().astype(int)
    cand_lons = lon_vals[idxs2]
 
    scored = []
    for la in cand_lats:
        for lo in cand_lons:
            r = risk_at(float(la), float(lo), age_group)
            scored.append((r, float(la), float(lo)))
    scored.sort(key=lambda t: t[0])  # 위험도 낮은 순
 
    chosen: list[tuple[float, float]] = []
    min_sep_m = max(150.0, haversine_m(start_lat, start_lng, end_lat, end_lng) * 0.08)
    for _, la, lo in scored:
        if all(haversine_m(la, lo, cla, clo) >= min_sep_m for cla, clo in chosen):
            chosen.append((la, lo))
        if len(chosen) >= MAX_CANDIDATES:
            break
    return chosen
 
 
def _safety_label(avg_risk: float) -> str:
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
 
 
def _tmap_route_result(key: str, label: str, tmap_result: dict, age_group: str) -> dict:
    path = tmap_result["path"]
    distance_m = tmap_result["distance_m"] if tmap_result["distance_m"] is not None else None
    duration_s = tmap_result["duration_s"]
    if distance_m is None:
        # Tmap이 총거리를 안 줬으면 좌표들로 근사 계산
        distance_m = sum(
            haversine_m(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
            for i in range(len(path) - 1)
        )
    avg_risk = _sample_path_risk(path, age_group)
    duration_min = round(duration_s / 60.0) if duration_s else max(1, round(distance_m / WALK_SPEED_M_PER_MIN))
    return {
        "type": key,
        "label": label,
        "distance_m": round(distance_m, 1),
        "avg_risk": round(avg_risk, 3),
        "duration_min": max(1, duration_min),
        "safety_label": _safety_label(avg_risk),
        "path": [{"lat": round(la, 6), "lng": round(lo, 6)} for la, lo in path],
    }
 
 
def _tmap_compute_routes(start_lat, start_lng, end_lat, end_lng, age_group: str) -> dict:
    """Tmap 보행자 API로 실제 도로 형상의 2경로(최단/안심우선)를 만든다.
 
    Tmap 자체는 위험도 기반 경로를 지원하지 않으므로, 우리가 risk_at()으로 뽑은
    저위험 경유지 후보들을 하나씩 넣어 Tmap을 다시 호출해보고, 그중 실제로 평균
    위험도가 낮아지는 경로를 "안심 우선"으로 채택한다. 후보 호출이 전부
    실패하거나 개선이 없으면 "최단" 경로를 그대로 재사용한다(그래도 실제 도로
    형상은 유지됨).
    """
    straight_m = haversine_m(start_lat, start_lng, end_lat, end_lng)
    if straight_m > MAX_STRAIGHT_M:
        raise RouteError(f"출발지-도착지 직선거리({straight_m/1000:.1f}km)가 프로토타입 지원 범위를 벗어났습니다.")
    if straight_m < 5:
        raise RouteError("출발지와 도착지가 너무 가깝습니다.")
 
    base = tmap_client.fetch_pedestrian_route(start_lat, start_lng, end_lat, end_lng)
    fast = _tmap_route_result("fast", "최단", base, age_group)
 
    candidates = []
    try:
        waypoints = _candidate_waypoints(start_lat, start_lng, end_lat, end_lng, age_group)
    except Exception:
        waypoints = []
 
    for wp in waypoints:
        try:
            r = tmap_client.fetch_pedestrian_route(start_lat, start_lng, end_lat, end_lng, pass_list=[wp])
        except tmap_client.TmapError:
            continue
        candidates.append(_tmap_route_result("candidate", "후보", r, age_group))
 
    def pick_variant(key: str, label: str, max_distance_ratio: float, fallback: dict) -> dict:
        pool = [c for c in candidates if c["distance_m"] <= fallback["distance_m"] * max_distance_ratio]
        pool = [c for c in pool if c["avg_risk"] < fallback["avg_risk"]]
        if not pool:
            picked = dict(fallback)
        else:
            picked = min(pool, key=lambda c: c["avg_risk"])
        picked = dict(picked)
        picked["type"] = key
        picked["label"] = label
        return picked
 
    safe = pick_variant("safe", "안심 우선", 1.8, fast)
 
    routes = {"fast": fast, "safe": safe}
    return {
        "start": {"lat": start_lat, "lng": start_lng},
        "end": {"lat": end_lat, "lng": end_lng},
        "age_group": age_group,
        "straight_distance_m": round(straight_m, 1),
        "routes": routes,
        "engine": "tmap",
        "note": (
            "Tmap(SK Open API) 보행자 경로 API로 계산한 실제 도로(보도) 기반 경로입니다. "
            "안심 우선 경로는 실측 CCTV·보안등·Wi-Fi·파출소 접근성 및 연령대별 TOP10 "
            "취약지역 근접도(risk_at)가 낮은 경유지를 지나도록 Tmap에 재요청해 선택한 결과입니다."
        ),
    }
 
 
def compute_routes(start_lat, start_lng, end_lat, end_lng, age_group: str) -> dict:
    """공개 엔트리포인트. Tmap이 설정돼 있으면 Tmap 기반, 아니면(또는 실패 시) 격자 폴백."""
    tmap_error: str | None = None
    if tmap_client.is_configured():
        try:
            return _tmap_compute_routes(start_lat, start_lng, end_lat, end_lng, age_group)
        except RouteError:
            raise
        except tmap_client.TmapError as exc:
            tmap_error = str(exc)
        except Exception as exc:  # 예상 못한 오류도 폴백으로 안전하게 처리 (사용자에게는 경로가 나가야 함)
            tmap_error = f"예상 못한 오류: {exc!r}"
        print(f"[routing] Tmap 호출 실패, 격자 폴백으로 전환: {tmap_error}", flush=True)
 
    result = _compute_routes_grid(start_lat, start_lng, end_lat, end_lng, age_group)
    if tmap_error is not None:
        # 디버깅 편의를 위해 실패 사유를 응답에도 그대로 노출한다 (배포 후 원인 파악용).
        result["tmap_error"] = tmap_error
    elif not tmap_client.is_configured():
        result["tmap_error"] = "TMAP_APP_KEY 미설정"
    return result
