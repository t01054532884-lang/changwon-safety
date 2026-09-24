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

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from scoring import FACILITIES, facility_score, grade_from_score, nearest_top10, protection_score_at
import routing

app = FastAPI(title="창원 안심길 Safety & Route API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/health")
def health():
    return {"ok": True, "cctv": len(FACILITIES["cctv"]["coords"]), "light": len(FACILITIES["light"]["coords"]),
            "wifi": len(FACILITIES["wifi"]["coords"]), "police": len(FACILITIES["police"]["coords"])}


# ---------- 정적 프론트엔드 서빙 (반드시 맨 마지막에 등록: /api/* 라우트가 우선 매칭되도록) ----------
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
