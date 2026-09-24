"""Tmap(SK Open API) 보행자 경로 안내 API 클라이언트.

https://tmapapi.sktelecom.com 의 "보행자 경로안내" API를 호출한다.
- 환경변수 TMAP_APP_KEY 가 없거나, 호출이 실패(네트워크/HTTP 오류/응답 파싱 실패)하면
  TmapError 를 던진다. 호출부(routing.py)는 이 경우 기존 격자 기반 방식으로
  자동 폴백해야 한다 — 이 모듈 자체는 절대 프로세스를 죽이면 안 된다.
- API 키는 코드/저장소에 절대 하드코딩하지 않는다. 배포 환경(Render 등)의
  환경변수로만 주입한다.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

TMAP_APP_KEY = os.environ.get("TMAP_APP_KEY", "").strip()
TMAP_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json"
TMAP_POI_URL = "https://apis.openapi.sk.com/tmap/pois"
TMAP_GEOCODE_URL = "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo"
TIMEOUT_S = 6.0


class TmapError(Exception):
    """Tmap 호출/파싱 실패 — 호출부는 이 예외를 잡아 격자 기반 방식으로 폴백한다."""


def is_configured() -> bool:
    return bool(TMAP_APP_KEY)


def fetch_pedestrian_route(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    pass_list: Optional[list[tuple[float, float]]] = None,
) -> dict:
    """Tmap 보행자 경로 API를 호출해 실제 도로(보도)를 따라가는 경로를 받아온다.

    pass_list: 경유지 좌표 목록 [(lat, lng), ...] (있으면 Tmap의 passList 파라미터로 전달)

    반환: {"path": [(lat, lng), ...], "distance_m": float | None, "duration_s": float | None}
    실패 시 TmapError.
    """
    if not TMAP_APP_KEY:
        raise TmapError("TMAP_APP_KEY 환경변수가 설정되지 않았습니다.")

    body = {
        "startX": str(start_lng),
        "startY": str(start_lat),
        "endX": str(end_lng),
        "endY": str(end_lat),
        "startName": "start",
        "endName": "end",
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
    }
    if pass_list:
        # Tmap passList 형식: "lng,lat_lng,lat_..." (경유지 여러 개는 밑줄로 구분)
        body["passList"] = "_".join(f"{lng},{lat}" for lat, lng in pass_list)

    try:
        resp = requests.post(
            TMAP_URL,
            json=body,
            headers={"appKey": TMAP_APP_KEY, "Content-Type": "application/json"},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise TmapError(f"Tmap API 호출 실패(네트워크): {exc}") from exc

    if resp.status_code != 200:
        raise TmapError(f"Tmap API 오류 응답: HTTP {resp.status_code} {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise TmapError(f"Tmap 응답 JSON 파싱 실패: {exc}") from exc

    features = data.get("features", [])
    if not features:
        raise TmapError(f"Tmap 응답에 경로 정보가 없습니다: {data}")

    total_distance = None
    total_time = None
    coords: list[tuple[float, float]] = []  # (lat, lng), 실제 도로 형상

    for feat in features:
        props = feat.get("properties", {}) or {}
        if total_distance is None and props.get("totalDistance") is not None:
            total_distance = props.get("totalDistance")
        if total_time is None and props.get("totalTime") is not None:
            total_time = props.get("totalTime")

        geom = feat.get("geometry", {}) or {}
        if geom.get("type") == "LineString":
            for lng, lat in geom.get("coordinates", []):
                coords.append((lat, lng))

    if not coords:
        raise TmapError("Tmap 응답에서 경로 좌표(LineString)를 추출하지 못했습니다.")

    return {
        "path": coords,
        "distance_m": float(total_distance) if total_distance is not None else None,
        "duration_s": float(total_time) if total_time is not None else None,
    }


def search_pois(keyword: str, count: int = 8, center_lat: Optional[float] = None, center_lng: Optional[float] = None) -> list[dict]:
    """Tmap POI(장소) 검색 API. 네이버 지도처럼 "창원 도서관" 같은 자유 검색어로
    실제 존재하는 모든 장소(도서관/공원/상가/랜드마크 등)를 폭넓게 찾기 위해 사용한다.

    이 앱의 destinations.json은 도서관·공원·파출소·어린이집·경로당 등 사전에 정리해둔
    한정된 목록이라, "NC파크"처럼 목록에 없는 장소는 애초에 검색이 안 되는 한계가 있다.
    이 함수는 그 한계를 보완하기 위한 것.

    ⚠️ 참고: 이 응답 구조(특히 poi 리스트/딕셔너리 형태, 좌표 필드명)는 Tmap 공식 문서를
    실시간으로 열람하지 못하는 환경에서 일반적으로 알려진 형태를 근거로 방어적으로 작성한
    것이라, 실제 배포 환경에서 처음 호출해보기 전까지는 100% 확신할 수 없다. 파싱이 실패하면
    TmapError에 원본 응답 일부를 그대로 담아서, 실제 구조를 보고 바로 고칠 수 있게 했다.

    반환: [{"name":, "lat":, "lng":, "address": str|None}, ...] (최대 count개). 실패 시 TmapError.
    """
    if not TMAP_APP_KEY:
        raise TmapError("TMAP_APP_KEY 환경변수가 설정되지 않았습니다.")

    params = {
        "version": "1",
        "searchKeyword": keyword,
        "resCoordType": "WGS84GEO",
        "reqCoordType": "WGS84GEO",
        "count": str(count),
        "page": "1",
    }
    if center_lat is not None and center_lng is not None:
        # 창원 인근 결과를 우선하도록 중심 좌표를 함께 전달(지원 안 되면 Tmap이 그냥 무시할 것)
        params["centerLat"] = str(center_lat)
        params["centerLon"] = str(center_lng)

    try:
        resp = requests.get(
            TMAP_POI_URL,
            params=params,
            headers={"appKey": TMAP_APP_KEY},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise TmapError(f"Tmap POI 검색 호출 실패(네트워크): {exc}") from exc

    if resp.status_code != 200:
        raise TmapError(f"Tmap POI 검색 오류 응답: HTTP {resp.status_code} {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise TmapError(f"Tmap POI 응답 JSON 파싱 실패: {exc}") from exc

    try:
        raw_pois = data["searchPoiInfo"]["pois"]["poi"]
    except (KeyError, TypeError) as exc:
        raise TmapError(f"Tmap POI 응답 구조가 예상과 다릅니다: {str(data)[:500]}") from exc

    if isinstance(raw_pois, dict):
        raw_pois = [raw_pois]  # 결과가 1개일 때 Tmap이 리스트 대신 딕셔너리를 주는 경우 방어
    if not isinstance(raw_pois, list):
        raise TmapError(f"Tmap POI 응답의 poi 필드 형식이 예상과 다릅니다: {type(raw_pois)}")

    results = []
    for poi in raw_pois:
        name = poi.get("name")
        lat_raw = poi.get("noorLat") or poi.get("frontLat") or poi.get("lat")
        lng_raw = poi.get("noorLon") or poi.get("frontLon") or poi.get("lng")
        if not name or lat_raw is None or lng_raw is None:
            continue
        try:
            lat = float(lat_raw)
            lng = float(lng_raw)
        except (TypeError, ValueError):
            continue
        address_parts = [poi.get("upperAddrName"), poi.get("middleAddrName"), poi.get("lowerAddrName")]
        address = " ".join(p for p in address_parts if p) or None
        results.append({"name": name, "lat": lat, "lng": lng, "address": address})

    return results


def geocode_address(address: str) -> Optional[dict]:
    """Tmap 지오코딩(주소→좌표 변환) API.

    사용자 피드백(2026-09-24): "도착지 검색이 왜 자유주소검색을 막아놨냐" —
    실제로 search_pois()는 destinations.json과 마찬가지로 "이름이 있는 장소"를
    찾는 방식이라, "창원시 성산구 중앙대로 151"처럼 이름 없는 순수 도로명/지번 주소를
    그대로 입력하면 검색이 안 될 수 있다. 이 함수는 그 경우를 위한 별도 경로다.

    사용자가 도로명주소/지번주소 중 어느 쪽으로 입력했는지, 건물번호를 포함했는지
    미리 알 수 없으므로 Tmap의 addressFlag 네 가지(F00·F02·F01·F03)를 순서대로
    시도해서 좌표가 나오는 첫 결과를 쓴다.

    ⚠️ 참고: search_pois()와 마찬가지로 이 API의 정확한 응답 필드명은 실시간 문서
    열람이 안 되는 환경에서 일반적으로 알려진 형태를 근거로 방어적으로 작성한 것이라,
    실제 배포 환경에서 처음 호출해보기 전까지 100% 확신할 수 없다. 네 가지 형식을
    다 시도해도 "구조 자체가 이상해서" 실패하면(HTTP 오류/JSON 파싱 실패) TmapError로
    원본 응답을 담아 던지고, 반대로 구조는 정상인데 "그냥 이 주소를 못 찾은 것"이면
    (좌표 후보가 0개) 에러가 아니라 None을 반환한다.

    반환: {"name": str, "lat": float, "lng": float, "address": str} | None (못 찾음).
    구조적 실패 시 TmapError.
    """
    if not TMAP_APP_KEY:
        raise TmapError("TMAP_APP_KEY 환경변수가 설정되지 않았습니다.")

    structural_errors: list[str] = []

    for flag in ("F00", "F02", "F01", "F03"):
        params = {
            "version": "1",
            "format": "json",
            "fullAddr": address,
            "coordType": "WGS84GEO",
            "addressFlag": flag,
        }
        try:
            resp = requests.get(
                TMAP_GEOCODE_URL, params=params,
                headers={"appKey": TMAP_APP_KEY}, timeout=TIMEOUT_S,
            )
        except requests.RequestException as exc:
            structural_errors.append(f"[{flag}] 네트워크 오류: {exc}")
            continue

        if resp.status_code != 200:
            structural_errors.append(f"[{flag}] HTTP {resp.status_code} {resp.text[:200]}")
            continue

        try:
            data = resp.json()
        except ValueError as exc:
            structural_errors.append(f"[{flag}] JSON 파싱 실패: {exc}")
            continue

        coord_info = data.get("coordinateInfo")
        if not isinstance(coord_info, dict):
            structural_errors.append(f"[{flag}] coordinateInfo 없음: {str(data)[:300]}")
            continue

        candidates = coord_info.get("coordinate")
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not candidates:
            continue  # 구조는 정상, 이 형식으로는 그냥 결과가 없음 -> 다음 flag 시도

        c = candidates[0]
        lat_raw = c.get("newLat") or c.get("lat") or c.get("noorLat")
        lng_raw = c.get("newLon") or c.get("lon") or c.get("noorLon")
        if lat_raw is None or lng_raw is None:
            structural_errors.append(f"[{flag}] 좌표 필드 없음: {str(c)[:300]}")
            continue
        try:
            lat = float(lat_raw)
            lng = float(lng_raw)
        except (TypeError, ValueError):
            structural_errors.append(f"[{flag}] 좌표 값 파싱 실패: {lat_raw}, {lng_raw}")
            continue
        if lat == 0.0 and lng == 0.0:
            continue

        name_parts = [c.get("bldNm"), c.get("roadName")]
        addr_parts = [c.get("upperAddrName"), c.get("middleAddrName"), c.get("lowerAddrName"), c.get("roadName")]
        seen_addr = []
        for p in addr_parts:
            if p and p not in seen_addr:
                seen_addr.append(p)
        return {
            "name": " ".join(p for p in name_parts if p) or address,
            "lat": lat,
            "lng": lng,
            "address": " ".join(seen_addr) or address,
        }

    if len(structural_errors) == 4:
        # 네 가지 시도 전부 "구조 자체가 이상해서" 실패 -> 우리 파싱 가정이 틀렸을
        # 가능성이 높으니, 조용히 None을 반환하는 대신 원본 응답을 실어서 던진다.
        raise TmapError("Tmap 지오코딩 응답 구조가 예상과 다릅니다: " + " | ".join(structural_errors))

    # 일부는 구조가 정상이었지만(그냥 결과 0개), 진짜로 이 주소를 못 찾은 것
    return None
