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
