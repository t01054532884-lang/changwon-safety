# 창원 안심길 (시민용 PWA)

창원시 취약계층(어린이·고령자) 안전 인프라 분석을 바탕으로 만든 시민용 안전 경로 앱입니다.
기존 chatgpt.site 배포본은 폐기하고 이 폴더에 새로 설계·개발했습니다(2026-09-24 결정).

## 구조

```
citizen-app/
├── frontend/   PWA 프론트엔드 (순수 HTML/CSS/JS, 프레임워크 없음)
├── backend/    FastAPI 백엔드 — /api/safety, /api/route + frontend 정적 서빙
├── dev-tools/  Playwright 스크린샷 테스트 스크립트(개발용, 배포에는 포함 안 됨)
└── render.yaml Render 배포 설정(Blueprint)
```

백엔드가 프론트엔드를 같은 프로세스에서 함께 서빙합니다. 그래서 로컬이든 배포든 **주소가
하나**입니다 — `/`로 접속하면 앱 화면, `/api/safety` `/api/route` `/api/health`로는 API가
동작합니다.

## 로컬 실행

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# http://localhost:8000/ 접속
```

저장소의 `data/`(CCTV·보안등·Wi-Fi·파출소·TOP10 등 실측 데이터)는 상대경로로 자동 인식됩니다.

## 배포 (Render)

1. https://render.com 가입 → New → Blueprint
2. 이 GitHub 저장소(changwon-safety) 연결 → `citizen-app/render.yaml` 자동 인식
3. Apply → 몇 분 후 `https://<서비스이름>.onrender.com` 발급
   - 이 주소 하나로 앱 + API가 전부 동작
   - Tmap 등 외부 API 앱 등록 시 "서비스 URL"로 이 주소 사용
   - 무료 티어는 무요청 시 슬립 → 첫 요청 시 콜드 스타트(수십 초) 발생 가능

## 알려진 한계 / 다음 작업

- `backend/README.md`에 상세 기록. 핵심은: (1) `/api/route`가 아직 실제 도로망이 아닌 격자
  근사 경로라는 점(Tmap 보행자 API 연동 예정, 키 발급 대기 중), (2) 도착지 검색이 자유 주소가
  아닌 사전 정리된 장소 목록(`frontend/data/destinations.json`) 기반이라는 점.
- 이 프로젝트 세션(Claude 코딩 샌드박스)은 네이버/카카오/Tmap 등 외부 지도 API 서버에 직접
  네트워크로 접근할 수 없어서, 그런 연동은 여기서 코드를 작성해도 이 샌드박스 안에서는 실행
  검증이 안 됩니다. 실제 배포 환경(Render 등)에서 최종 확인이 필요합니다.
