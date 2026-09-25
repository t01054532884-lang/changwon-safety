"""창원 안심길 — Stage 2/3 백엔드 (+ 프론트엔드 정적 서빙).

1) /api/safety : 임의의 위도/경도에 대해 CCTV·보안등·공공Wi-Fi·파출소 접근성 점수
   (analysis/vulnerability.py 로직 재사용) + 가장 가까운 어린이/노인 TOP10 취약지역 거리
2) /api/route  : 출발지→도착지 최단/균형/안심우선 3경로 (routing.py, Stage 3 신규)
3) 그 외 모든 경로 : ../frontend(PWA 정적 파일)를 그대로 서빙 — 배포 시 백엔드와 프론트를
   같은 도메인 하나로 띄워서(동일 출처) 공개 주소를 하나만 발급받으면 되게 했다
   (Tmap 등 외부 API 앱 등록에 필요한 "서비스 URL" 하나로 충분하도록).

※ 실제 범죄위험(생활안전지도 WMS) 레이어는 API KEY가 없어 도시 전역에 대해
재현할 수 없다. 그래서 TOP10 근접 여부를 보조 신호로만 사용하고, 이 사실을
응답의 note 필드에 항상 명시한다. (추후 WMS 키가 확보되면 이 부분을 교체할 것)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scoring import FACILITIES, facility_score, grade_from_score, nearest_top10, protection_score_at
import routing
import tmap_client
import reports_store

app = FastAPI(title="창원 안심길 Safety & Route API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

reports_store.init_db()  # Stage 4: 위험신고 SQLite 저장소 초기화(테이블 없으면 생성)


@app.get("/api/safety")
def get_safety(lat: float = Query(...), lng: float = Query(...), age_group: str = Query("adult")):
    scores = {key: facility_score(lat, lng, key) for key in FACILITIES}
    protection_score = protection_score_at(lat, lng)
    hotspot = nearest_top10(lat, lng, age_group)
    infra_grade, grade = grade_from_score(protection_score, hotspot)

    return {
        "lat": lat, "lng": lng, "age_group": age_group,
        "protection_score": round(protection_score, 1),
        "infra_grade": infra_grade,
        "grade": grade,
        "facilities": scores,
        "nearest_top10": hotspot,
        "note": (
            "grade는 CCTV/보안등/Wi-Fi/파출소 접근성(실측 데이터) 기반 등급을 "
            "기본으로 하고, 알려진 TOP10 취약지역 근접 시에만 하향 보정한 잠정 지표입니다. "
            "생활안전지도 WMS 범죄위험 API 키가 연동되면 도시 전역 실제 범죄위험을 반영해 교체할 예정입니다."
        ),
    }


@app.get("/api/route")
def get_route(
    start_lat: float = Query(...),
    start_lng: float = Query(...),
    end_lat: float = Query(...),
    end_lng: float = Query(...),
    age_group: str = Query("adult"),
):
    try:
        return routing.compute_routes(start_lat, start_lng, end_lat, end_lng, age_group)
    except routing.RouteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/search-place")
def search_place(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=15),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
):
    """자유 검색어로 실제 장소를 찾는다(Tmap POI 검색). destinations.json에 없는 장소
    (예: NC파크 같은 상가·랜드마크)도 찾을 수 있도록 프론트엔드의 사전 정리된 목록 검색을
    보완하는 용도. Tmap 키가 없거나 호출이 실패하면 빈 목록 + error 필드를 반환하고,
    프론트엔드는 이 경우 기존 destinations.json 검색 결과만으로 계속 동작한다."""
    try:
        places = tmap_client.search_pois(q, count=limit, center_lat=lat, center_lng=lng)
        return {"source": "tmap", "places": places}
    except tmap_client.TmapError as exc:
        return {"source": "none", "places": [], "error": str(exc)}


@app.get("/api/geocode-address")
def geocode_address(q: str = Query(..., min_length=1)):
    """자유 주소 검색(지오코딩). destinations.json에도 없고 Tmap POI 검색(장소명 기반)에도
    안 걸리는 순수 도로명/지번 주소(예: "창원시 성산구 중앙대로 151")를 그대로 입력했을 때,
    그 주소의 좌표를 찾기 위한 엔드포인트. 프론트엔드는 목록/POI 검색이 둘 다 실패했을 때만
    이걸 마지막으로 호출한다."""
    try:
        result = tmap_client.geocode_address(q)
    except tmap_client.TmapError as exc:
        return {"found": False, "error": str(exc)}
    if result is None:
        return {"found": False}
    return {"found": True, "place": result}


class ReportCreate(BaseModel):
    report_type: str
    description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    age_group: Optional[str] = None
    image_data_url: Optional[str] = Field(
        default=None, description="data:image/...;base64,... 형식의 첨부 이미지(선택)"
    )


class ReportStatusUpdate(BaseModel):
    status: str
    admin_note: Optional[str] = None


@app.post("/api/reports")
def create_report(payload: ReportCreate):
    """위험신고 접수 (Stage 4). 시민 앱에서 호출한다."""
    try:
        report_id = reports_store.create_report(
            report_type=payload.report_type,
            description=payload.description,
            lat=payload.lat,
            lng=payload.lng,
            age_group=payload.age_group,
            image_data_url=payload.image_data_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "id": report_id}


@app.get("/api/reports")
def get_reports(
    status: Optional[str] = Query(None, description="접수됨/확인중/처리완료/반려 중 하나로 필터링"),
    include_image: bool = Query(False, description="true면 각 신고의 이미지 데이터까지 포함(응답이 커짐)"),
):
    """위험신고 목록 조회 (Stage 4/6). 관리자 웹에서 호출한다."""
    return {"reports": reports_store.list_reports(status=status, include_image=include_image)}


@app.get("/api/reports/{report_id}")
def get_report_detail(report_id: int):
    report = reports_store.get_report(report_id, include_image=True)
    if report is None:
        raise HTTPException(status_code=404, detail="해당 신고를 찾을 수 없습니다.")
    return report


@app.patch("/api/reports/{report_id}")
def patch_report(report_id: int, payload: ReportStatusUpdate):
    """신고 처리 상태 변경 (Stage 6). 관리자 웹에서 호출한다."""
    try:
        updated = reports_store.update_report_status(report_id, payload.status, payload.admin_note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="해당 신고를 찾을 수 없습니다.")
    return {"ok": True}


@app.get("/api/config")
def get_public_config():
    """프론트엔드가 지도 표시(홈/안심경로)에 필요로 하는 공개 설정값.

    2026-09-26: 지도 표시 엔진을 Leaflet+OpenStreetMap(키 불필요) → 네이버 지도 JS SDK로
    교체하면서 추가. 여기서 반환하는 Client ID는 브라우저에 그대로 노출되는 걸 전제로
    하는 값이다(비밀키가 아님) — 네이버 지도 JS SDK는 애초에 "이 Client ID로 어떤 도메인
    에서 호출해도 되는지"를 네이버클라우드 콘솔의 Web 서비스 URL 허용 목록으로 막는
    방식이라, 그 목록에 이 서비스의 도메인이 등록돼 있어야만 실제로 지도가 뜬다
    (admin/app.py도 이미 같은 값을 화면에 그대로 노출하고 있음). 그래서 다른 API 키들과
    달리 이 값은 .env/Render 환경변수에만 두면 되고, 별도 인증 처리는 필요 없다."""
    return {
        "naverMapClientId": os.environ.get("NAVER_MAP_CLIENT_ID", "").strip(),
    }


@app.get("/api/health")
def health():
    return {"ok": True, "cctv": len(FACILITIES["cctv"]["coords"]), "light": len(FACILITIES["light"]["coords"]),
            "wifi": len(FACILITIES["wifi"]["coords"]), "police": len(FACILITIES["police"]["coords"])}


# ---------- 정적 프론트엔드 서빙 (반드시 맨 마지막에 등록: /api/* 라우트가 우선 매칭되도록) ----------
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
