/* 창원 안심길 — Stage 1 프로토타입 (프론트엔드 뼈대)
 * - 실제 전체 격자 안전도 API는 Stage 2~3에서 연결 예정
 * - 여기서는 저장소(changwon-safety)의 실제 TOP10 데이터를 정적으로 불러와 사용
 */

const CHANGWON_CENTER = [35.2280, 128.6811]; // 창원시청 부근 fallback 좌표

// Stage 2~3: 안전도/경로 API. 백엔드가 이 프론트엔드를 같은 오리진에서 함께 서빙하므로
// 기본값은 상대경로("")로 두면 배포 도메인이 어디든 그대로 작동한다.
// 로컬에서 프론트엔드/백엔드를 각각 다른 포트로 따로 띄워 테스트할 때만 window.ANSHIMGIL_API_BASE로 override.
const SAFETY_API_BASE = window.ANSHIMGIL_API_BASE || "";

const state = {
  profile: { ageGroup: null, gender: null },
  location: null, // {lat, lng}
  topZones: { child: null, senior: null }, // 내부 계산용(안전도 API 폴백/향후 경로 가중치), 홈 화면에는 미노출
  recommendedPlaces: [], // 도서관/공원/지구대 등 홈 화면 추천시설
  destinations: [], // 안심경로 도착지 검색용 장소 목록(도서관/공원/파출소/어린이집/경로당/랜드마크)
  routeDestination: null, // 안심경로에서 선택된 도착지 {name, lat, lng}
  // 안심경로 출발지 수동 지정(2026-09-25 추가): null이면 기존처럼 실시간 위치(state.location)를
  // 그대로 출발지로 쓰고, 값이 있으면(사용자가 "✏️ 수정"으로 직접 검색해 고른 장소) 그 좌표를
  // 출발지로 쓴다. state.location은 홈 탭/위험신고 등 다른 곳에서도 계속 쓰이므로 건드리지 않고
  // 별도 필드로 분리했다.
  routeStart: null, // {name, lat, lng} | null
  routeResult: null, // 최근 /api/route 응답
  selectedRouteType: "safe",
  activeTab: "home",
  savedPlaces: [], // 저장(북마크) 탭 — 자주 가는 곳 최대 5개, 이 기기의 localStorage에만 저장
};

// ---------- 유틸 ----------
function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function gradeColor(grade) {
  return { 5: "var(--grade-5)", 4: "var(--grade-4)", 3: "var(--grade-3)", 2: "var(--grade-2)", 1: "var(--grade-1)" }[grade] || "#94a3b8";
}
function gradeLabel(grade) {
  return { 5: "매우안전", 4: "안전", 3: "보통", 2: "위험", 1: "매우위험" }[grade] || "확인중";
}

function saveProfile() {
  try { localStorage.setItem("ac_profile", JSON.stringify(state.profile)); } catch (e) {}
}
function loadProfile() {
  try {
    const raw = localStorage.getItem("ac_profile");
    if (raw) state.profile = JSON.parse(raw);
  } catch (e) {}
}

// ---------- 온보딩 ----------
// 2026-09-26: 온보딩을 마치고 프로필이 저장돼 있어도, 예전에는 앱을 다시 열 때마다
// 온보딩(위치 허용→연령대→성별)을 처음부터 다시 거쳐야 했다(저장된 값을 그냥
// 덮어쓰는 구조). 이제는 이미 저장된 프로필이 있으면 온보딩 화면 자체를 건너뛰고
// 바로 앱으로 들어간다 — 연령대/성별을 나중에 고치고 싶으면 헤더의 프로필 버튼으로
// 언제든 다시 고를 수 있다(initProfileEdit).
function enterApp() {
  document.getElementById("onboarding")?.remove();
  document.getElementById("app").hidden = false;
  updateProfileChip();
  initApp();
}

function initOnboarding() {
  const steps = ["location", "age", "gender"];
  let stepIndex = 0;

  function showStep(name) {
    document.querySelectorAll(".ob-step").forEach(el => {
      el.hidden = el.dataset.step !== name;
    });
  }

  function finishOnboarding() {
    saveProfile();
    enterApp();
  }

  document.getElementById("btn-allow-location").addEventListener("click", () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        pos => {
          state.location = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          showStep("age");
        },
        () => { showStep("age"); },
        { enableHighAccuracy: true, timeout: 6000 }
      );
    } else {
      showStep("age");
    }
  });
  document.getElementById("btn-skip-location").addEventListener("click", () => showStep("age"));

  document.getElementById("age-choices").addEventListener("click", (e) => {
    const card = e.target.closest(".choice-card");
    if (!card) return;
    state.profile.ageGroup = card.dataset.value;
    showStep("gender");
  });

  document.getElementById("gender-choices").addEventListener("click", (e) => {
    const card = e.target.closest(".choice-card");
    if (!card) return;
    state.profile.gender = card.dataset.value;
    finishOnboarding();
  });
}

function updateProfileChip() {
  const map = { child: "🧒 어린이 모드", adult: "🧑 성인 모드", senior: "🧓 고령자 모드" };
  document.getElementById("profile-chip").textContent = map[state.profile.ageGroup] || "🙂 프로필";
}

// 2026-09-26 추가: "온보딩 때 연령대/성별을 잘못 눌렀을 수도 있는데, 홈이나 안심경로에
// 들어간 뒤에도 바꿀 수 있으면 좋겠다"는 요청 — 헤더의 프로필 버튼(모든 탭에서 항상
// 보이는 위치)을 눌러 언제든 다시 고를 수 있게 한다. 온보딩과 같은 choice-card를
// 재사용하되, 탭을 넘기지 않고 그 자리에서 바로 값이 바뀌고 시트만 닫히는 방식이다.
function syncProfileEditSelection() {
  document.querySelectorAll("#profile-age-choices .choice-card").forEach(card => {
    card.classList.toggle("is-selected", card.dataset.value === state.profile.ageGroup);
  });
  document.querySelectorAll("#profile-gender-choices .choice-card").forEach(card => {
    card.classList.toggle("is-selected", card.dataset.value === state.profile.gender);
  });
}

function openProfileEdit() {
  syncProfileEditSelection();
  document.getElementById("profile-edit").hidden = false;
}

function closeProfileEdit() {
  document.getElementById("profile-edit").hidden = true;
}

function initProfileEdit() {
  document.getElementById("profile-chip").addEventListener("click", openProfileEdit);
  document.getElementById("btn-close-profile-edit").addEventListener("click", closeProfileEdit);

  document.getElementById("profile-age-choices").addEventListener("click", (e) => {
    const card = e.target.closest(".choice-card");
    if (!card) return;
    state.profile.ageGroup = card.dataset.value;
    saveProfile();
    updateProfileChip();
    syncProfileEditSelection();
    // 홈 지도의 "주의 구간"은 연령대별 TOP10을 참고하므로 즉시 다시 그려준다
    // (마커가 아직 없으면 renderRecommendedPlaces 내부 가드가 알아서 건너뜀).
    renderRecommendedPlaces();
  });

  document.getElementById("profile-gender-choices").addEventListener("click", (e) => {
    const card = e.target.closest(".choice-card");
    if (!card) return;
    state.profile.gender = card.dataset.value;
    saveProfile();
    syncProfileEditSelection();
  });
}

// 2026-09-26 추가: 아직 실사용자에게 배포하지 않은 테스트 단계라, 실기기 GPS 없이도
// 창원시 여러 지점에서 앱을 확인해볼 수 있어야 한다는 요청으로 추가한 개발용 버튼.
// 백엔드 /api/random-location이 창원시 행정구역 경계(BOUNDARY, scoring.py의 동일한
// point_in_polygon 로직 재사용) 내부에서 뽑아준 좌표를 실제 GPS 위치처럼 그대로
// state.location에 덮어쓰고, 실시간 위치 갱신과 완전히 같은 경로(refreshLiveLocationUI)
// 를 태워 마커·추천 장소·안전도 등이 전부 그 좌표 기준으로 다시 계산되게 한다.
function initAdminRandomLocation() {
  const btn = document.getElementById("btn-admin-random-location");
  if (!btn) return;
  const originalLabel = btn.textContent;
  let resetTimer = null;

  btn.addEventListener("click", async () => {
    if (resetTimer) clearTimeout(resetTimer);
    btn.disabled = true;
    btn.textContent = "위치 찾는 중…";
    try {
      const res = await fetch("/api/random-location");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      state.location = { lat: data.lat, lng: data.lng };
      // 실시간 위치 갱신(watchPosition)과 달리 이건 순간이동이라, 지도가 새 위치를
      // 따라가지 못하고 마커만 화면 밖 어딘가에서 움직이는 것처럼 보일 수 있다 —
      // 홈 지도를 새 좌표로 직접 재중심시켜준다.
      if (homeMap) homeMap.setView([data.lat, data.lng], 15);
      refreshLiveLocationUI();
      console.log("[admin-random-location] 새 테스트 위치:", data.lat, data.lng);
      btn.textContent = "✅ 이동됨";
    } catch (e) {
      console.error("[admin-random-location] 위치 뽑기 실패:", e);
      btn.textContent = "⚠️ 실패";
    } finally {
      resetTimer = setTimeout(() => {
        btn.textContent = originalLabel;
        btn.disabled = false;
      }, 1600);
    }
  });
}

// ---------- 탭 네비게이션 ----------
function initTabs() {
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}
function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("is-active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach(p => p.hidden = p.dataset.tab !== tab);
  if (tab === "home" && homeMap) setTimeout(() => homeMap.invalidateSize(), 50);
  if (tab === "route" && routeMap) setTimeout(() => routeMap.invalidateSize(), 50);
}

// 2026-09-24: "경로 찾으면 지도가 반절 짤린다"는 제보 — 폰에서 도착지 입력할 때 키보드가
// 올라왔다 내려가면서 화면(뷰포트) 크기가 바뀌는데, 그 시점에 지도 크기를 다시 계산하는
// 코드가 없어서 생긴 문제로 추정된다(탭 전환할 때만 invalidateSize를 불렀음). 키보드가
// 내려가거나 화면 방향이 바뀌는 등 뷰포트 크기가 바뀔 때마다 "현재 보이는" 지도만 골라
// 크기를 다시 맞추도록 보강한다 — 원인이 이게 아니더라도 이렇게 해두면 손해는 없다.
function resyncVisibleMapSize() {
  if (state.activeTab === "home" && homeMap) homeMap.invalidateSize();
  if (state.activeTab === "route" && routeMap) routeMap.invalidateSize();
}
function initMapResizeSafety() {
  window.addEventListener("resize", resyncVisibleMapSize);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", resyncVisibleMapSize);
  }
  // 도착지 입력창에서 포커스가 빠질 때(키보드가 내려가는 시점)도 한 번 더 보정
  document.getElementById("route-end")?.addEventListener("blur", () => setTimeout(resyncVisibleMapSize, 250));
}

// ---------- 지도 / 안전도 (홈) ----------
let homeMap, routeMap;

async function loadTopZones() {
  // TOP10 취약지역 데이터는 홈 화면에는 더 이상 노출하지 않고,
  // (1) 안전도 API 폴백 계산, (2) 추후 안심경로 안전가중치 계산용으로만 내부에서 사용한다.
  const [child, senior] = await Promise.all([
    fetch("data/child_top10.geojson").then(r => r.json()),
    fetch("data/elderly_top10.geojson").then(r => r.json()),
  ]);
  state.topZones.child = child;
  state.topZones.senior = senior;
}

async function loadRecommendedPlaces() {
  const data = await fetch("data/recommended_places.json").then(r => r.json());
  state.recommendedPlaces = data.places;
}

function currentZoneSet() {
  // 성인은 어린이+노인 취약지역을 모두 참고정보로 함께 표시
  if (state.profile.ageGroup === "child") return state.topZones.child;
  if (state.profile.ageGroup === "senior") return state.topZones.senior;
  return null;
}

let recommendedLayer; // 추천시설 마커 레이어(위치 갱신 시마다 다시 그리므로 그룹으로 관리)
let safetyTriangleLayer; // "안전요소 3종 충족" 초록 삼각형 마커 레이어(2026-09-26 추가)

// 2026-09-25 추가(2차 수정): setTimeout 120ms로 홈 지도 크기를 강제 보정해봤지만 실기기
// 스크린샷에서 여전히 빈 화면으로 남는 사례가 확인됨. 홈 지도 컨테이너(#map-home)는
// position:absolute; inset:0 로 부모(.app-main) 높이에 맞춰지는데, 이 부모의 실제 높이는
// 폰트 로딩·동적 뷰포트 단위(dvh) 계산 등으로 페이지 로드 초반엔 아직 확정 안 돼 있을 수
// 있다 — 반대로 안심경로 지도(.map-short)는 CSS에 height:220px가 고정값으로 박혀 있어서
// 이런 타이밍 문제에서 자유로웠고, 그래서 그쪽만 먼저 고쳐진 것으로 보인다.
// 특정 지연시간을 추측하는 대신, 컨테이너의 "실제 렌더링 크기가 바뀌는 순간"을
// ResizeObserver로 직접 감지해서 그때마다 invalidateSize()를 불러주도록 일반화한다 —
// 0×0에서 실제 크기로 바뀌는 최초 순간은 물론, 이후 키보드가 열리거나 화면 회전이 있을
// 때도 전부 이 하나의 메커니즘으로 커버된다. (구형 브라우저 등 ResizeObserver가 없는
// 경우를 대비해 기존 setTimeout 보정도 그대로 남겨둔다 — 두 경로가 겹쳐도 invalidateSize를
// 한 번 더 부르는 것뿐이라 문제 없음.)
function watchMapContainerSize(elementId, getMapWrapper, label) {
  const el = document.getElementById(elementId);
  if (!el || typeof ResizeObserver === "undefined") {
    console.log("[naver-map][" + (label || elementId) + "] ResizeObserver 사용 불가 또는 엘리먼트 없음");
    return;
  }
  let lastW = 0, lastH = 0;
  const ro = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry) return;
    const { width, height } = entry.contentRect;
    console.log("[naver-map][" + (label || elementId) + "] ResizeObserver 콜백, 크기:", width, height);
    // 2026-09-25 콘솔 로그로 확인: 네이버 지도 SDK가 초기화되면서 컨테이너에 직접
    // 인라인 height(때로는 width)를 0으로 박아버리는 경우가 있었다(우리 CSS보다
    // 인라인 스타일이 우선순위가 높아서 그대로 찌그러짐). 폭은 정상인데 높이만(또는
    // 그 반대) 0인 비정상적인 경우 인라인 값을 지워서 우리 CSS가 다시 크기를
    // 결정하게 강제한다 — 지우는 것 자체가 또 한 번의 resize를 유발해 정상 크기로
    // 다시 측정된다.
    if (el.style.height || el.style.width) {
      console.log(
        "[naver-map][" + (label || elementId) + "] 인라인 크기 발견, 제거함 (height=" +
          el.style.height + ", width=" + el.style.width + ")"
      );
      el.style.removeProperty("height");
      el.style.removeProperty("width");
      return; // 스타일 제거로 다시 콜백이 불릴 것이므로 이번 콜백에서는 여기서 멈춤
    }
    if (width <= 0 || height <= 0) return; // 아직 크기가 안 잡혔으면 다음 변화를 기다림
    if (width === lastW && height === lastH) return; // 같은 크기로 중복 호출 방지
    lastW = width;
    lastH = height;
    const wrapper = getMapWrapper();
    if (wrapper) wrapper.invalidateSize();
  });
  ro.observe(el);
}

function initHomeMap() {
  // 2026-09-25 추가: ResizeObserver/setTimeout 보정을 다 넣어봤는데도 실기기에서
  // 홈 지도가 계속 빈 화면으로 남는다는 제보가 이어져, 더 이상 추측만으로 고치기보다
  // 실제 콘솔 로그를 받아서 정확한 원인을 잡기 위한 진단 로그를 임시로 추가한다
  // (naver-map-shim.js의 [NMap] 로그와 짝을 이룸). 문제가 해결되면 나중에 정리해도 됨.
  console.log("[naver-map][home] initHomeMap 시작, state.location:", state.location);

  const center = state.location ? [state.location.lat, state.location.lng] : CHANGWON_CENTER;
  homeMap = NMap.map("map-home", { zoomControl: false }).setView(center, state.location ? 15 : 12);
  // 네이버 지도는 Map 생성 시 자체 타일을 그려주므로 별도 타일 레이어 추가가 필요 없다.

  // 홈은 앱이 열리자마자 이미 활성 탭이라 switchTab()의 invalidateSize를 한 번도 못
  // 거친다 — 아래 두 가지로 이중 보정한다.
  setTimeout(() => { if (homeMap) homeMap.invalidateSize(); }, 120);
  watchMapContainerSize("map-home", () => homeMap, "home");

  recommendedLayer = NMap.layerGroup().addTo(homeMap);
  safetyTriangleLayer = NMap.layerGroup().addTo(homeMap);
  // 2026-09-25 추가: 이 두 함수 중 하나가 조용히 예외를 던지면 이후 코드(안심경로 지도
  // 생성 포함)까지 통째로 멈출 수 있어서, 문제를 격리하기 위해 각각 try/catch로 감쌈.
  try {
    renderRecommendedPlaces();
  } catch (e) {
    console.error("[naver-map][home] renderRecommendedPlaces 중 예외:", e);
  }
  try {
    renderSafetyTriangles();
  } catch (e) {
    console.error("[naver-map][home] renderSafetyTriangles 중 예외:", e);
  }
  try {
    refreshLiveLocationUI();
  } catch (e) {
    console.error("[naver-map][home] refreshLiveLocationUI 중 예외:", e);
  }
  console.log("[naver-map][home] initHomeMap 완료");
}

const PLACE_STYLE = {
  library: { color: "#2563eb", emoji: "📚", label: "도서관" },
  park: { color: "#16a34a", emoji: "🌳", label: "공원" },
  police: { color: "#4f46e5", emoji: "🚓", label: "지구대·파출소" },
};

// ---------- 홈 지도 "귀여운" 안전/주의 구간 표시 (2026-09-24 추가) ----------
// 등급 배지·숫자 점수는 여전히 노출하지 않되(2026-09-24 이전 결정 유지),
// 실측 데이터 기반 안전시설 근처("안전 영향권")와 취약지역 인근("주의 구간")을
// 은은한 색 번짐 + 아이콘 배지로만 시각화한다.
const SAFE_ZONE_COLOR = "#0f9d78";
const CAUTION_ZONE_COLOR = "#e2554a";
const CAUTION_ZONE_MAX_DIST_M = 3000; // 이보다 멀면 홈 지도에 주의 구간을 표시하지 않음

function addGlowZone(layerGroup, lat, lng, baseRadius, color) {
  [
    { r: baseRadius * 1.9, opacity: 0.06 },
    { r: baseRadius * 1.35, opacity: 0.11 },
    { r: baseRadius, opacity: 0.18 },
  ].forEach(ring => {
    NMap.circle([lat, lng], {
      radius: ring.r, stroke: false, fillColor: color, fillOpacity: ring.opacity,
      interactive: false,
    }).addTo(layerGroup);
  });
}

function shieldDivIcon() {
  return NMap.divIcon({
    className: "facility-badge",
    html: `<div class="facility-badge-inner">` +
      `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#fff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">` +
      `<path d="M12 3l7 3v5c0 5-3.3 8.4-7 10-3.7-1.6-7-5-7-10V6l7-3z"/></svg></div>`,
    iconSize: [32, 32], iconAnchor: [16, 16],
  });
}

function cautionDivIcon() {
  return NMap.divIcon({
    className: "facility-badge",
    html: `<div class="facility-badge-inner facility-badge-caution">` +
      `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#fff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">` +
      `<path d="M12 3.5l9 15.5H3z"/><line x1="12" y1="9.5" x2="12" y2="13.2"/><circle cx="12" cy="16" r="0.35" fill="#fff" stroke="none"/></svg></div>`,
    iconSize: [32, 32], iconAnchor: [16, 16],
  });
}

// 2026-09-26 추가: 관리자 웹 지도에 이미 있는 "안전요소 3종 충족"(CCTV+보안등+공공Wi-Fi가
// 모두 가까운 지점) 초록 삼각형(△)을 시민 앱 홈 지도에도 그대로 옮겨왔다 — admin/app.py
// (admin/naver_map.py)의 safe-support-triangle과 같은 흰 테두리+초록 삼각형 모양.
function safetyTriangleDivIcon() {
  return NMap.divIcon({
    html: `<div style="filter: drop-shadow(0 2px 2px rgba(20,83,45,.5));">` +
      `<svg width="26" height="24" viewBox="0 0 30 28">` +
      `<polygon points="15,2 28,26 2,26" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round"/>` +
      `<polygon points="15,2 28,26 2,26" fill="rgba(22,163,74,.10)" stroke="#16a34a" stroke-width="3" stroke-linejoin="round"/>` +
      `</svg></div>`,
    iconSize: [26, 24], iconAnchor: [13, 23],
  });
}

function nearestHotspot(zoneSet, lat, lng) {
  if (!zoneSet || !Array.isArray(zoneSet.features) || !zoneSet.features.length) return null;
  let best = null, bestDist = Infinity;
  zoneSet.features.forEach(f => {
    const props = f.properties || {};
    if (props.latitude == null || props.longitude == null) return;
    const d = haversineM(lat, lng, props.latitude, props.longitude);
    if (d < bestDist) { bestDist = d; best = { lat: props.latitude, lng: props.longitude, dist: d }; }
  });
  return best;
}

function renderRecommendedPlaces() {
  const places = state.recommendedPlaces || [];
  const withDist = places.map(p => ({
    ...p,
    dist: state.location ? haversineM(state.location.lat, state.location.lng, p.lat, p.lng) : null,
  }));
  withDist.sort((a, b) => (a.dist ?? 1e9) - (b.dist ?? 1e9));
  const nearestThree = withDist.slice(0, 3);

  if (recommendedLayer) {
    recommendedLayer.clearLayers();

    // 안전 영향권: 가장 가까운 추천시설(도서관/공원/파출소) 최대 3곳만 은은하게 표시
    nearestThree.forEach(p => {
      const style = PLACE_STYLE[p.category] || { emoji: "📍", label: p.category };
      addGlowZone(recommendedLayer, p.lat, p.lng, 120, SAFE_ZONE_COLOR);
      NMap.marker([p.lat, p.lng], { icon: shieldDivIcon(), interactive: true })
        .addTo(recommendedLayer)
        .bindPopup(`<strong>🛡️ ${p.name}</strong><br/>${style.label} · 안전 영향권`);
    });

    // 주의 구간: 연령대별 TOP10 취약지역 중 가장 가까운 한 곳만, 너무 멀면 표시하지 않음
    if (state.location) {
      const zoneSet = currentZoneSet();
      const hotspot = nearestHotspot(zoneSet, state.location.lat, state.location.lng);
      if (hotspot && hotspot.dist <= CAUTION_ZONE_MAX_DIST_M) {
        addGlowZone(recommendedLayer, hotspot.lat, hotspot.lng, 130, CAUTION_ZONE_COLOR);
        NMap.marker([hotspot.lat, hotspot.lng], { icon: cautionDivIcon(), interactive: true })
          .addTo(recommendedLayer)
          .bindPopup("<strong>⚠️ 주의 구간</strong><br/>실측 데이터 기준 안전 인프라 보완이 필요한 구간이에요");
      }
    }
  }

  const ul = document.getElementById("nearby-list");
  ul.innerHTML = "";
  nearestThree.forEach(item => {
    const style = PLACE_STYLE[item.category] || { color: "#64748b", emoji: "📍", label: item.category };
    const li = document.createElement("li");
    const distText = item.dist != null ? `${(item.dist / 1000).toFixed(1)}km` : "거리 확인 불가";
    li.innerHTML = `<span>${style.emoji} ${item.name} <small style="color:#94a3b8">· ${style.label}</small></span>` +
      `<span class="tag" style="background:${style.color}">${distText}</span>`;
    ul.appendChild(li);
  });
  if (nearestThree.length === 0) {
    ul.innerHTML = "<li>주변 추천시설 정보를 불러오지 못했어요.</li>";
  }
}

// 2026-09-26 추가: 관리자 웹 지도에 이미 있는 "안전요소 3종 충족"(CCTV+보안등+공공Wi-Fi)
// 초록 삼각형을 시민 앱 홈 지도에도 표시. 도시 전역이 아니라 /api/safety-triangles가
// 내 위치 주변 반경만 걸러서 주므로, 여기서는 그 결과를 그대로 그리기만 한다.
// GPS가 몇 초마다 갱신될 때마다 매번 다시 요청하면 낭비이므로, 마지막으로 불러온
// 지점에서 일정 거리 이상 움직였을 때만 다시 불러온다(안심경로 화살표 방향 계산과
// 같은 방식의 스로틀링).
let lastTriangleFetchAt = null;
const TRIANGLE_REFRESH_MIN_MOVE_M = 80;

function triangleGlow(lat, lng) {
  NMap.circle([lat, lng], {
    radius: 26, stroke: false, fillColor: "#16a34a", fillOpacity: 0.10, interactive: false,
  }).addTo(safetyTriangleLayer);
}

async function renderSafetyTriangles() {
  if (!homeMap || !safetyTriangleLayer || !state.location) return;
  const { lat, lng } = state.location;

  if (lastTriangleFetchAt) {
    const moved = haversineM(lastTriangleFetchAt.lat, lastTriangleFetchAt.lng, lat, lng);
    if (moved < TRIANGLE_REFRESH_MIN_MOVE_M) return; // 크게 안 움직였으면 다시 불러오지 않음
  }
  lastTriangleFetchAt = { lat, lng };

  try {
    const res = await fetch(`/api/safety-triangles?lat=${lat}&lng=${lng}&radius_m=700&limit=30`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!safetyTriangleLayer) return; // 응답 오는 사이 지도가 없어졌을 수도 있음
    safetyTriangleLayer.clearLayers();
    (data.sites || []).forEach(site => {
      triangleGlow(site.lat, site.lng);
      NMap.marker([site.lat, site.lng], { icon: safetyTriangleDivIcon(), interactive: true })
        .addTo(safetyTriangleLayer)
        .bindPopup(
          `<strong style="color:#15803d">안전요소 3종 충족 △</strong><br/>` +
          `CCTV 최근접 ${Math.round(site.cctv_distance_m)}m · 보안등 최근접 ${Math.round(site.light_distance_m)}m<br/>` +
          `<small style="color:#6b7280">CCTV·보안등·공공Wi-Fi가 모두 가까운 지점이에요. ` +
          `시설 접근성을 나타내며 절대적인 안전을 보장하지는 않아요.</small>`
        );
    });
  } catch (e) {
    console.error("[safety-triangles] 불러오기 실패:", e);
  }
}

// 참고: 홈 화면 등급 배지(안전도 API 연동)는 사용자 피드백(2026-09-24)에 따라
// "위험성을 유발한다"는 이유로 홈 화면에서 제거했다. /api/safety 자체는 계속 살려두고
// Stage 3 안심경로(경로별 안전도 비교)에서 재사용할 예정이다.

// ---------- 실시간 위치 추적 (Stage 3 추가: 위치가 바뀔 때마다 내 위치 아이콘도 이동) ----------
let userMarkerHome = null;
let userMarkerRoute = null;
let locationWatchId = null;

// 안심경로 지도 전용: 이동 방향(heading)을 계산해 파란 화살표를 그 방향으로 회전시킨다.
// (홈 지도는 사용자 요청(2026-09-24)에 따라 방향 표시 없이 단순 점으로 유지)
let lastBearingFix = null; // 직전 위치(화살표 방향 계산용, GPS 노이즈 방지를 위해 일정 거리 이상 이동했을 때만 갱신)
let currentHeadingDeg = 0;
const BEARING_MIN_MOVE_M = 3; // 이보다 적게 움직였으면 방향을 갱신하지 않음(제자리 GPS 흔들림 방지)

function bearingDeg(lat1, lon1, lat2, lon2) {
  const toRad = (d) => d * Math.PI / 180;
  const phi1 = toRad(lat1), phi2 = toRad(lat2);
  const dLambda = toRad(lon2 - lon1);
  const y = Math.sin(dLambda) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLambda);
  const theta = Math.atan2(y, x);
  return (theta * 180 / Math.PI + 360) % 360;
}

function updateHeading(lat, lng) {
  if (lastBearingFix) {
    const moved = haversineM(lastBearingFix.lat, lastBearingFix.lng, lat, lng);
    if (moved >= BEARING_MIN_MOVE_M) {
      currentHeadingDeg = bearingDeg(lastBearingFix.lat, lastBearingFix.lng, lat, lng);
      lastBearingFix = { lat, lng };
    }
  } else {
    lastBearingFix = { lat, lng };
  }
}

function arrowDivIcon(headingDeg) {
  return NMap.divIcon({
    className: "user-arrow-icon",
    html: `<div class="user-arrow-inner" style="transform: rotate(${headingDeg}deg)">` +
      `<svg viewBox="0 0 24 24" width="28" height="28">` +
      `<path d="M12 2.5 L20 20.5 L12 16 L4 20.5 Z" fill="#1d4ed8" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/>` +
      `</svg></div>`,
    iconSize: [30, 30], iconAnchor: [15, 15],
  });
}

function startLocationWatch() {
  if (!navigator.geolocation || !navigator.geolocation.watchPosition) return;
  if (locationWatchId != null) return; // 중복 등록 방지
  locationWatchId = navigator.geolocation.watchPosition(
    (pos) => {
      state.location = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      refreshLiveLocationUI();
    },
    () => { /* 위치 갱신 실패 시 마지막으로 알던 위치를 그대로 유지 */ },
    { enableHighAccuracy: true, maximumAge: 4000, timeout: 12000 }
  );
}

function updateReportLocationText() {
  const locationText = document.getElementById("report-location-text");
  if (!locationText) return;
  locationText.textContent = state.location
    ? `위도 ${state.location.lat.toFixed(5)}, 경도 ${state.location.lng.toFixed(5)}`
    : "위치 정보 없음 (권한을 허용해주세요)";
}

function refreshLiveLocationUI() {
  if (!state.location) return;
  const latlng = [state.location.lat, state.location.lng];

  if (homeMap) {
    // 홈 지도는 방향 표시 없이 단순한 점으로 유지(사용자 요청, 2026-09-24)
    if (!userMarkerHome) {
      userMarkerHome = NMap.circleMarker(latlng, {
        radius: 8, color: "#1d4ed8", fillColor: "#1d4ed8", fillOpacity: 0.9, weight: 3,
      }).addTo(homeMap).bindPopup("내 위치(실시간)");
    } else {
      userMarkerHome.setLatLng(latlng);
    }
  }

  if (routeMap) {
    // 안심경로 지도는 이동 방향을 알 수 있는 파란 화살표로 표시(사용자 요청, 2026-09-24)
    updateHeading(state.location.lat, state.location.lng);
    if (!userMarkerRoute) {
      userMarkerRoute = NMap.marker(latlng, { icon: arrowDivIcon(currentHeadingDeg) })
        .addTo(routeMap).bindPopup("내 위치(실시간)");
    } else {
      userMarkerRoute.setLatLng(latlng);
      userMarkerRoute.setIcon(arrowDivIcon(currentHeadingDeg));
    }
    // 2026-09-26 추가: 화살표는 이미 실시간으로 움직이고 있었지만, 지도 화면 자체는
    // 처음 지정한 위치에 고정돼 있어서 많이 걸으면 화살표가 화면 밖으로 나가버리는
    // 문제가 있었다("경로만 뜨고 내 위치를 못 따라간다"는 요청) — 안심경로 탭을
    // 보고 있는 동안에는 위치가 갱신될 때마다 지도를 내 위치로 같이 이동시킨다.
    // 줌 레벨은 건드리지 않아(panTo) 사용자가 손으로 확대/축소해둔 상태는 유지된다.
    if (state.activeTab === "route") routeMap.panTo(latlng);
  }

  if (state.activeTab === "home") {
    renderRecommendedPlaces();
    renderSafetyTriangles();
  }
  if (state.activeTab === "report") updateReportLocationText();
}

// ---------- 안심경로 (Stage 3: 실제 라우팅 엔진 연결) ----------
let routeLayers; // 경로 폴리라인/마커 레이어 그룹

const DEST_CATEGORY_STYLE = {
  library: { color: "#2563eb", emoji: "📚", label: "도서관" },
  park: { color: "#16a34a", emoji: "🌳", label: "공원" },
  police: { color: "#4f46e5", emoji: "🚓", label: "지구대·파출소" },
  childcare: { color: "#db2777", emoji: "🧸", label: "어린이집" },
  senior_center: { color: "#ca8a04", emoji: "🏠", label: "경로당" },
  landmark: { color: "#0f766e", emoji: "📍", label: "주요 장소" },
  tmap_poi: { color: "#7c3aed", emoji: "🔍", label: "검색결과" },
  address: { color: "#0891b2", emoji: "🏠", label: "주소" },
};

const ROUTE_TYPE_COLOR = { fast: "#94a3b8", balanced: "#f97316", safe: "#16a34a" };

function initRouteMap() {
  routeMap = NMap.map("route-map", { zoomControl: false }).setView(
    state.location ? [state.location.lat, state.location.lng] : CHANGWON_CENTER, 13
  );
  routeLayers = NMap.layerGroup().addTo(routeMap);
  // 안심경로 탭은 처음엔 hidden 상태로 생성되므로, 나중에 탭을 열 때 실제 크기를 갖게
  // 되는 순간을 여기서도 감지해둔다(홈 지도와 같은 이유 — watchMapContainerSize 참고).
  watchMapContainerSize("route-map", () => routeMap, "route");
}

async function loadDestinations() {
  const data = await fetch("data/destinations.json").then(r => r.json());
  state.destinations = data.places;
}

function searchLocalDestinations(query, limit = 8) {
  // 2026-09-24 버그 수정 (2차): "창원 도서관"처럼 띄어쓰기가 들어간 검색어는 원래
  // 전체 문자열을 그대로 부분일치시켜서(예: "창원 도서관"이라는 글자가 이름에 그대로
  // 들어있어야 함) 실제로는 어떤 장소도 못 찾았다. 이제는 띄어쓰기 기준으로 단어를
  // 나눠서 "모든 단어를 포함하는" 이름을 찾도록 바꿨다(예: "창원", "도서관" 둘 다
  // 포함하면 "창원중앙도서관"도 찾아짐) — 네이버 지도 등 일반적인 장소 검색과 비슷한 방식.
  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  const ageTag = state.profile.ageGroup === "child" ? "child" : state.profile.ageGroup === "senior" ? "senior" : null;
  return state.destinations
    .map(p => {
      const name = p.name.toLowerCase();
      if (!tokens.every(t => name.includes(t))) return null;
      const baseRank = name.startsWith(tokens[0]) ? 0 : 1; // 첫 단어로 시작하는 이름을 더 우선
      // 연령대 태그는 baseRank가 같을 때만 순서를 살짝 조정하는 보조 기준으로만 쓴다
      // (예전엔 이 보정이 너무 세서, 어린이 모드에서 "창원"을 검색하면 어린이집만 잔뜩
      // 뜨고 도서관·공원은 아예 안 보이는 문제가 있었음).
      const ageBoost = (ageTag && p.ageTag === ageTag) ? 0 : 1;
      return { ...p, baseRank, ageBoost };
    })
    .filter(Boolean)
    .sort((a, b) => (a.baseRank - b.baseRank) || (a.ageBoost - b.ageBoost))
    .slice(0, limit);
}

// destinations.json은 도서관/공원/파출소/어린이집/경로당 등 미리 정리해둔 한정된
// 목록이라 "NC파크"처럼 목록에 없는 장소는 원래 검색이 안 됐다(사용자 피드백,
// 2026-09-24: 네이버 지도 API를 쓸 때는 이런 게 없었는데 왜 빠졌냐는 지적).
// 그래서 Tmap POI 검색(/api/search-place, 자유 검색어로 실제 존재하는 모든 장소를
// 찾는 API)을 함께 붙여서, 목록에 없는 장소도 찾을 수 있게 보완했다. 목록 검색은
// 그대로 즉시 뜨고, Tmap 검색 결과는 조금 늦게 도착하면 뒤에 이어 붙는다.
async function searchTmapPlaces(query, limit = 6) {
  try {
    const url = `${SAFETY_API_BASE}/api/search-place?q=${encodeURIComponent(query)}&limit=${limit}` +
      (state.location ? `&lat=${state.location.lat}&lng=${state.location.lng}` : "");
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    if (data.error) console.warn("[search-place] Tmap 검색 실패(무시하고 목록 검색만 사용):", data.error);
    return (data.places || []).map(p => ({ ...p, category: "tmap_poi" }));
  } catch (e) {
    console.warn("[search-place] 요청 실패(무시하고 목록 검색만 사용):", e);
    return [];
  }
}

// 2026-09-24: "도착지는 왜 자유주소검색을 막아놨냐"는 지적 — 실제로는 두 가지가 겹쳐서
// 막고 있었다. (1) destinations.json/Tmap POI 검색 둘 다 "이름이 있는 장소"를 찾는
// 방식이라, "창원시 성산구 중앙대로 151" 같은 순수 도로명/지번 주소는 애초에 검색 결과에
// 안 뜰 수 있었고, (2) 그것과 별개로 "경로 찾기" 버튼이 목록에서 클릭으로 골라야만
// 눌리게 돼 있어서, 설령 주소가 검색됐어도 클릭 안 하고 그냥 엔터/버튼을 누르면 막혔다.
// 이 함수는 (1)을 풀기 위한 것 — Tmap의 주소→좌표 변환(지오코딩) API를 호출한다.
async function geocodeAddress(query) {
  try {
    const url = `${SAFETY_API_BASE}/api/geocode-address?q=${encodeURIComponent(query)}`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) console.warn("[geocode-address] 실패(무시):", data.error);
    return data.found ? data.place : null;
  } catch (e) {
    console.warn("[geocode-address] 요청 실패(무시):", e);
    return null;
  }
}

function mergeDestinationResults(local, remote, limit = 10) {
  const seen = new Set(local.map(p => p.name));
  const merged = local.slice();
  remote.forEach(p => {
    if (seen.has(p.name)) return;
    seen.add(p.name);
    merged.push(p);
  });
  return merged.slice(0, limit);
}

// 2026-09-25 추가: "출발지를 항상 내 현재 위치로만 쓰는데, 다른 곳에서 출발하는 경로도
// 찾아보고 싶다"는 요청 — 출발지 옆 "✏️ 수정" 버튼을 누르면 도착지와 똑같은 방식(목록 검색
// → Tmap POI 검색 → 지오코딩)으로 출발지를 직접 검색해서 고를 수 있게 한다. 목록 맨 위에는
// 항상 "📍 내 현재 위치" 항목을 고정으로 넣어서 언제든 실시간 위치로 되돌릴 수 있게 했다.
function initRouteStartAutocomplete() {
  const input = document.getElementById("route-start");
  const list = document.getElementById("route-start-suggestions");
  const editBtn = document.getElementById("btn-edit-start");
  let searchToken = 0;

  function displayCurrentStart() {
    input.value = state.routeStart ? state.routeStart.name : "내 현재 위치";
  }

  function closeList() { list.hidden = true; list.innerHTML = ""; }

  function exitEditMode() {
    input.readOnly = true;
    displayCurrentStart();
    closeList();
  }

  function selectUseCurrentLocation() {
    state.routeStart = null;
    exitEditMode();
  }

  function selectStart(place) {
    state.routeStart = { name: place.name, lat: place.lat, lng: place.lng };
    exitEditMode();
  }

  function enterEditMode() {
    input.readOnly = false;
    input.value = "";
    input.focus();
    renderList([]);
  }

  function renderList(places) {
    list.innerHTML = "";

    const pinned = document.createElement("li");
    pinned.innerHTML = `<span>📍 내 현재 위치</span><small>실시간 위치</small>`;
    pinned.addEventListener("mousedown", (e) => { e.preventDefault(); selectUseCurrentLocation(); });
    list.appendChild(pinned);

    if (!places.length && input.value.trim()) {
      const empty = document.createElement("li");
      empty.className = "suggestion-empty";
      empty.textContent = "일치하는 장소가 없어요";
      list.appendChild(empty);
    } else {
      places.forEach(p => {
        const style = DEST_CATEGORY_STYLE[p.category] || { emoji: "📍", label: p.category };
        const li = document.createElement("li");
        li.innerHTML = `<span>${style.emoji} ${p.name}</span><small>${style.label}</small>`;
        li.addEventListener("mousedown", (e) => { e.preventDefault(); selectStart(p); });
        list.appendChild(li);
      });
    }
    list.hidden = false;
  }

  input.addEventListener("input", async () => {
    const myToken = ++searchToken;
    const query = input.value;

    const localMatches = searchLocalDestinations(query);
    renderList(localMatches);

    if (!query.trim()) return;
    const remoteMatches = await searchTmapPlaces(query);
    if (myToken !== searchToken) return;
    renderList(mergeDestinationResults(localMatches, remoteMatches));
  });

  // 도착지처럼 Enter로도 바로 확정할 수 있게: 목록에 없어도 한 번 더(로컬→Tmap POI→지오코딩)
  // 찾아본 뒤 가장 앞 결과를 출발지로 확정한다.
  input.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const rawQuery = input.value.trim();
    if (!rawQuery) { selectUseCurrentLocation(); return; }

    editBtn.disabled = true;
    const [localMatches, remoteMatches] = await Promise.all([
      Promise.resolve(searchLocalDestinations(rawQuery, 1)),
      searchTmapPlaces(rawQuery, 1),
    ]);
    let place = localMatches[0] || remoteMatches[0] || null;
    if (!place) {
      const geocoded = await geocodeAddress(rawQuery);
      if (geocoded) place = { ...geocoded, category: "address" };
    }
    editBtn.disabled = false;

    if (place) {
      selectStart(place);
    } else {
      setRouteStatus("입력하신 출발지를 찾지 못했어요. 목록에서 골라보거나 다른 이름으로 다시 시도해주세요.", true);
    }
  });

  input.addEventListener("blur", () => setTimeout(() => { if (!input.readOnly) exitEditMode(); }, 150));

  editBtn.addEventListener("click", () => {
    if (input.readOnly) enterEditMode();
    else exitEditMode();
  });
}

function initRouteAutocomplete() {
  const input = document.getElementById("route-end");
  const list = document.getElementById("route-end-suggestions");
  const findBtn = document.getElementById("btn-find-route");
  let searchToken = 0; // 늦게 도착한 예전 검색 응답이 최신 입력 결과를 덮어쓰지 않도록

  function closeList() { list.hidden = true; list.innerHTML = ""; }

  function selectDestination(place) {
    state.routeDestination = place;
    input.value = place.name;
    closeList();
    findBtn.disabled = false;
  }

  function renderList(places) {
    if (!places.length) {
      list.innerHTML = input.value.trim() ? `<li class="suggestion-empty">일치하는 장소가 없어요</li>` : "";
      list.hidden = !input.value.trim();
      return;
    }
    list.innerHTML = "";
    places.forEach(p => {
      const style = DEST_CATEGORY_STYLE[p.category] || { emoji: "📍", label: p.category };
      const li = document.createElement("li");
      li.innerHTML = `<span>${style.emoji} ${p.name}</span><small>${style.label}</small>`;
      li.addEventListener("mousedown", (e) => { e.preventDefault(); selectDestination(p); });
      list.appendChild(li);
    });
    list.hidden = false;
  }

  input.addEventListener("input", async () => {
    state.routeDestination = null;
    // 2026-09-24 수정: 예전엔 여기서 버튼을 무조건 비활성화하고 목록 클릭으로만 다시
    // 켰는데, 그러면 이름/주소를 정확히 입력해도 클릭을 안 하면 "경로 찾기" 자체를
    // 누를 수 없었다("자유주소검색을 막아놨다"는 지적의 원인 중 하나). 이제는 입력한
    // 글자가 있으면 버튼을 눌러서 시도라도 해볼 수 있게 하고, 실제 매칭/지오코딩은
    // 버튼 클릭 시점에 처리한다.
    findBtn.disabled = !input.value.trim();
    const myToken = ++searchToken;
    const query = input.value;

    const localMatches = searchLocalDestinations(query);
    renderList(localMatches); // 목록 검색 결과는 항상 즉시 표시

    if (!query.trim()) return;
    const remoteMatches = await searchTmapPlaces(query);
    if (myToken !== searchToken) return; // 그 사이 사용자가 다른 검색어를 입력했으면 버림
    renderList(mergeDestinationResults(localMatches, remoteMatches));
  });

  input.addEventListener("blur", () => setTimeout(closeList, 120));
  input.addEventListener("focus", () => { if (input.value.trim() && !state.routeDestination) input.dispatchEvent(new Event("input")); });
}

function setRouteStatus(message, isError = false) {
  const el = document.getElementById("route-status");
  el.textContent = message || "";
  el.hidden = !message;
  el.classList.toggle("is-error", isError);
}

function renderRouteResult(data) {
  state.routeResult = data;

  // 지도가 아직 안 떠 있어도(네이버 지도 SDK 로딩 실패 등) 아래 경로 옵션 목록/시간·거리
  // 정보는 계속 보여준다 — 지도 관련 부분만 건너뛴다.
  if (routeMap && routeLayers) {
    routeLayers.clearLayers();

    NMap.circleMarker([data.start.lat, data.start.lng], { radius: 7, color: "#1d4ed8", fillColor: "#1d4ed8", fillOpacity: 0.95, weight: 3 })
      .addTo(routeLayers).bindPopup(state.routeStart ? `출발지 · ${state.routeStart.name}` : "출발지 · 내 현재 위치");
    NMap.circleMarker([data.end.lat, data.end.lng], { radius: 7, color: "#dc2626", fillColor: "#dc2626", fillOpacity: 0.95, weight: 3 })
      .addTo(routeLayers).bindPopup(state.routeDestination ? state.routeDestination.name : "도착지");

    const polylines = {};
    Object.entries(data.routes).forEach(([type, r]) => {
      const latlngs = r.path.map(p => [p.lat, p.lng]);
      polylines[type] = NMap.polyline(latlngs, {
        color: ROUTE_TYPE_COLOR[type], weight: type === state.selectedRouteType ? 6 : 3,
        opacity: type === state.selectedRouteType ? 0.95 : 0.45,
      }).addTo(routeLayers);
    });
    state._routePolylines = polylines;
  } else {
    state._routePolylines = null;
  }

  const options = document.getElementById("route-options");
  options.hidden = false;
  options.querySelectorAll(".route-option").forEach(row => {
    const type = row.dataset.type;
    const r = data.routes[type];
    row.classList.toggle("is-selected", type === state.selectedRouteType);
    if (!r) {
      row.querySelector(".route-time").textContent = "경로 없음";
      row.querySelector(".route-option-sub").textContent = "이 조건으로는 경로를 찾지 못했어요";
      row.disabled = true;
      return;
    }
    row.disabled = false;
    row.querySelector(".route-time").textContent = `도보 약 ${r.duration_min}분`;
    row.querySelector(".route-option-sub").textContent =
      `${(r.distance_m / 1000).toFixed(2)}km · 안전도 ${r.safety_label}`;
  });

  // 검색 직전에 도착지 입력창 포커스가 빠지면서 폰 키보드가 내려가고, 그 사이 지도
  // 크기가 바뀌었을 수 있다 — fitBounds로 화면을 맞추기 직전에 한 번 더 크기를
  // 재계산해서, 이미 사라진 키보드 공간만큼 지도가 반절 잘려 보이는 걸 방지한다.
  if (routeMap && state._routePolylines) {
    routeMap.invalidateSize();
    const selected = state._routePolylines[state.selectedRouteType];
    if (selected) routeMap.fitBounds(selected.getBounds(), { padding: [24, 24] });
  }
}

function highlightRouteType(type) {
  state.selectedRouteType = type;
  document.querySelectorAll(".route-option").forEach(o => o.classList.toggle("is-selected", o.dataset.type === type));
  if (!state._routePolylines) return;
  Object.entries(state._routePolylines).forEach(([t, line]) => {
    line.setStyle({ weight: t === type ? 6 : 3, opacity: t === type ? 0.95 : 0.45 });
    if (t === type) line.bringToFront();
  });
  const selected = state._routePolylines[type];
  if (routeMap && selected) routeMap.fitBounds(selected.getBounds(), { padding: [24, 24] });
}

// 안심경로 출발지 좌표를 돌려준다: 사용자가 "✏️ 수정"으로 직접 고른 장소가 있으면 그걸,
// 없으면 기존처럼 실시간 위치를 쓴다.
function getRouteStartPoint() {
  return state.routeStart || state.location;
}

// dest(좌표가 있는 장소 객체)로 실제 경로를 계산해서 그려준다. "경로 찾기" 버튼과
// 저장(북마크) 탭에서 저장해둔 장소를 클릭했을 때 둘 다 이 함수를 공유해서 쓴다.
async function computeAndRenderRoute(dest) {
  const start = getRouteStartPoint();
  if (!start) {
    setRouteStatus("현재 위치 정보가 없어 경로를 계산할 수 없어요. 위치 권한을 확인하거나 출발지를 직접 검색해주세요.", true);
    return;
  }

  const btn = document.getElementById("btn-find-route");
  btn.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = "경로 계산 중…";
  setRouteStatus("출발지 주변 안전도를 분석해 3가지 경로를 계산하고 있어요…");
  document.getElementById("route-options").hidden = true;

  const ageGroup = state.profile.ageGroup || "adult";
  const url = `${SAFETY_API_BASE}/api/route?start_lat=${start.lat}&start_lng=${start.lng}` +
    `&end_lat=${dest.lat}&end_lng=${dest.lng}&age_group=${ageGroup}`;

  try {
    const res = await fetch(url);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "경로를 계산하지 못했어요.");
    }
    const data = await res.json();
    state.selectedRouteType = "safe";
    renderRouteResult(data);
    setRouteStatus("");
  } catch (err) {
    setRouteStatus(err.message || "경로 계산 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.", true);
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

// 저장 탭에서 북마크한 장소를 클릭했을 때: 안심경로 탭으로 이동해서 도착지 칸을
// 채우고 바로 경로 계산까지 이어서 해준다(다시 검색할 필요 없이 한 번에).
async function goToSavedPlace(place) {
  switchTab("route");
  state.routeDestination = place;
  const endInput = document.getElementById("route-end");
  if (endInput) endInput.value = place.name;
  document.getElementById("btn-find-route").disabled = false;
  await computeAndRenderRoute(place);
}

function initRouteForm() {
  initRouteStartAutocomplete();
  initRouteAutocomplete();

  document.getElementById("btn-find-route").addEventListener("click", async () => {
    const endInput = document.getElementById("route-end");
    let dest = state.routeDestination;
    const rawQuery = endInput.value.trim();

    // 목록에서 클릭으로 고르지 않고 텍스트만 입력한 채로 눌렀을 때: (2026-09-24 수정)
    // 예전엔 여기서 바로 막았는데, 이러면 정확한 이름/주소를 입력해도 클릭을 안 하면
    // 무조건 실패했다. 이제는 누른 시점에 한 번 더 찾아본다 — 목록/Tmap 장소 검색으로
    // 안 걸리면 마지막으로 Tmap 지오코딩(순수 주소)까지 시도한다.
    if (!dest && rawQuery) {
      const btn0 = document.getElementById("btn-find-route");
      btn0.disabled = true;
      setRouteStatus("입력하신 내용으로 장소를 찾는 중…");

      const [localMatches, remoteMatches] = await Promise.all([
        Promise.resolve(searchLocalDestinations(rawQuery, 1)),
        searchTmapPlaces(rawQuery, 1),
      ]);
      dest = localMatches[0] || remoteMatches[0] || null;

      if (!dest) {
        const geocoded = await geocodeAddress(rawQuery);
        if (geocoded) dest = { ...geocoded, category: "address" };
      }

      if (dest) {
        state.routeDestination = dest;
        endInput.value = dest.name;
      }
      btn0.disabled = false;
    }

    if (!dest) {
      setRouteStatus("입력하신 장소/주소를 찾지 못했어요. 다른 이름이나 정확한 주소로 다시 시도해주세요.", true);
      endInput.focus();
      return;
    }

    await computeAndRenderRoute(dest);
  });

  document.getElementById("route-options").addEventListener("click", (e) => {
    const opt = e.target.closest(".route-option");
    if (!opt || opt.disabled) return;
    highlightRouteType(opt.dataset.type);
  });

  document.getElementById("btn-save-destination")?.addEventListener("click", () => {
    if (!state.routeDestination) return;
    const added = addSavedPlace(state.routeDestination);
    setRouteStatus(
      added ? `"${state.routeDestination.name}" 저장 탭에 저장했어요.` : "이미 저장했거나 저장 공간(5개)이 가득 찼어요.",
      !added
    );
  });
}

// ---------- 저장(북마크) ----------
// 2026-09-24: "저장 메뉴가 텅 비어있다, 자주 가는 곳을 북마크처럼 최대 5개 저장해서
// 클릭하면 바로 경로를 찍어줬으면 좋겠다"는 요청으로 새로 추가. 계정/서버 개념이
// 없는 앱이라 이 기기의 localStorage에만 저장한다(다른 기기와는 공유되지 않음).
const SAVED_PLACES_KEY = "anshimgil_saved_places_v1";
const SAVED_PLACES_MAX = 5;

function loadSavedPlaces() {
  try {
    const raw = localStorage.getItem(SAVED_PLACES_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    state.savedPlaces = Array.isArray(parsed) ? parsed.slice(0, SAVED_PLACES_MAX) : [];
  } catch (e) {
    state.savedPlaces = []; // 저장된 값이 깨져 있어도(다른 버전 형식 등) 앱이 죽지 않게
  }
}

function persistSavedPlaces() {
  try {
    localStorage.setItem(SAVED_PLACES_KEY, JSON.stringify(state.savedPlaces));
  } catch (e) {
    console.warn("[saved-places] 저장 실패(브라우저 저장 공간/프라이빗 모드 문제일 수 있음):", e);
  }
}

function isSamePlace(a, b) {
  if (a.name === b.name) return true;
  return Math.abs(a.lat - b.lat) < 0.0002 && Math.abs(a.lng - b.lng) < 0.0002; // 대략 20m 이내는 같은 곳으로 간주
}

function setSaveStatus(message, isError = false) {
  const el = document.getElementById("save-status");
  if (!el) return;
  el.textContent = message || "";
  el.hidden = !message;
  el.classList.toggle("is-error", isError);
  if (message) setTimeout(() => { if (el.textContent === message) el.hidden = true; }, 2600);
}

function addSavedPlace(place) {
  if (state.savedPlaces.some(p => isSamePlace(p, place))) {
    setSaveStatus("이미 저장된 장소예요.", true);
    return false;
  }
  if (state.savedPlaces.length >= SAVED_PLACES_MAX) {
    setSaveStatus(`최대 ${SAVED_PLACES_MAX}개까지만 저장할 수 있어요. 다른 장소를 먼저 삭제해주세요.`, true);
    return false;
  }
  state.savedPlaces.push({ name: place.name, lat: place.lat, lng: place.lng, category: place.category || "landmark" });
  persistSavedPlaces();
  renderSavedPlaces();
  return true;
}

function removeSavedPlace(index) {
  state.savedPlaces.splice(index, 1);
  persistSavedPlaces();
  renderSavedPlaces();
}

function renderSavedPlaces() {
  const list = document.getElementById("saved-places-list");
  const empty = document.getElementById("saved-places-empty");
  if (!list || !empty) return;
  list.innerHTML = "";
  empty.hidden = state.savedPlaces.length > 0;

  state.savedPlaces.forEach((place, index) => {
    const style = DEST_CATEGORY_STYLE[place.category] || { emoji: "📍", label: "저장한 장소" };
    const li = document.createElement("li");
    li.className = "saved-place-item";
    li.innerHTML =
      `<button class="saved-place-main" type="button">` +
        `<span class="saved-place-emoji">${style.emoji}</span>` +
        `<span class="saved-place-name">${place.name}</span>` +
      `</button>` +
      `<button class="saved-place-delete" type="button" aria-label="삭제">✕</button>`;
    li.querySelector(".saved-place-main").addEventListener("click", () => goToSavedPlace(place));
    li.querySelector(".saved-place-delete").addEventListener("click", (e) => {
      e.stopPropagation();
      removeSavedPlace(index);
    });
    list.appendChild(li);
  });
}

// 저장 탭 안의 "자주 가는 곳 추가" 검색창 — 안심경로 도착지 검색과 같은 3단계
// (목록 → Tmap 장소 검색 → 지오코딩)를 그대로 재사용해서, 여기서도 이름/주소
// 어느 쪽으로 검색해도 찾을 수 있게 한다.
function initSaveSearch() {
  const input = document.getElementById("save-search");
  const list = document.getElementById("save-search-suggestions");
  if (!input || !list) return;
  let searchToken = 0;

  function closeList() { list.hidden = true; list.innerHTML = ""; }

  function renderList(places) {
    if (!places.length) {
      list.innerHTML = input.value.trim() ? `<li class="suggestion-empty">일치하는 장소가 없어요</li>` : "";
      list.hidden = !input.value.trim();
      return;
    }
    list.innerHTML = "";
    places.forEach(p => {
      const style = DEST_CATEGORY_STYLE[p.category] || { emoji: "📍", label: p.category };
      const li = document.createElement("li");
      li.innerHTML = `<span>${style.emoji} ${p.name}</span><small>${style.label}</small>`;
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const added = addSavedPlace(p);
        if (added) {
          input.value = "";
          setSaveStatus(`"${p.name}" 저장했어요.`);
        }
        closeList();
      });
      list.appendChild(li);
    });
    list.hidden = false;
  }

  input.addEventListener("input", async () => {
    const myToken = ++searchToken;
    const query = input.value;
    const localMatches = searchLocalDestinations(query);
    renderList(localMatches);
    if (!query.trim()) return;
    const remoteMatches = await searchTmapPlaces(query);
    if (myToken !== searchToken) return;
    renderList(mergeDestinationResults(localMatches, remoteMatches));
  });
  input.addEventListener("blur", () => setTimeout(closeList, 120));
}

function initSaveTab() {
  loadSavedPlaces();
  initSaveSearch();
  renderSavedPlaces();
}

// ---------- 위험신고 ----------
// 첨부 이미지를 base64 data URL 문자열로 바꾼다(서버에 그대로 JSON으로 실어 보내기 위함).
function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error("파일을 읽지 못했어요."));
    reader.readAsDataURL(file);
  });
}

function setReportStatus(message, isError = false) {
  const el = document.getElementById("report-status");
  if (!el) return;
  el.textContent = message || "";
  el.hidden = !message;
  el.classList.toggle("is-error", isError);
}

// 2026-09-24 (Stage 4): 로컬 목업(console.log만 하던 것)을 실제 백엔드 저장으로 교체.
// /api/reports로 접수하면 관리자 웹의 "위험신고 접수함"에서 조회/상태 변경까지 이어진다.
function initReportForm() {
  const typeEl = document.getElementById("report-type");
  const descEl = document.getElementById("report-desc");
  const imageEl = document.getElementById("report-image");
  const preview = document.getElementById("report-image-preview");
  const submitBtn = document.getElementById("btn-submit-report");
  const form = document.getElementById("report-form");
  const toast = document.getElementById("report-toast");

  updateReportLocationText(); // 이후에는 실시간 위치 갱신 시 refreshLiveLocationUI()가 이 텍스트도 갱신

  function validate() {
    const hasType = !!typeEl.value;
    const hasContent = !!imageEl.files.length || descEl.value.trim().length > 0;
    submitBtn.disabled = !(hasType && hasContent);
  }
  typeEl.addEventListener("change", validate);
  descEl.addEventListener("input", validate);
  imageEl.addEventListener("change", () => {
    if (imageEl.files[0]) {
      preview.src = URL.createObjectURL(imageEl.files[0]);
      preview.hidden = false;
    } else {
      preview.hidden = true;
    }
    validate();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    setReportStatus("");
    submitBtn.disabled = true;
    const originalLabel = submitBtn.textContent;
    submitBtn.textContent = "접수하는 중…";

    try {
      let imageDataUrl = null;
      if (imageEl.files[0]) {
        imageDataUrl = await readFileAsDataUrl(imageEl.files[0]);
      }

      const payload = {
        report_type: typeEl.value,
        description: descEl.value.trim() || null,
        lat: state.location ? state.location.lat : null,
        lng: state.location ? state.location.lng : null,
        age_group: state.profile.ageGroup || null,
        image_data_url: imageDataUrl,
      };

      const res = await fetch(`${SAFETY_API_BASE}/api/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "신고 접수에 실패했어요.");
      }

      toast.hidden = false;
      setTimeout(() => { toast.hidden = true; }, 3200);
      form.reset();
      preview.hidden = true;
    } catch (err) {
      setReportStatus(err.message || "신고 접수 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.", true);
    } finally {
      submitBtn.textContent = originalLabel;
      validate();
    }
  });
}

// 2026-09-26: 지도 표시 엔진을 Leaflet+OpenStreetMap → 네이버 지도 JS SDK로 교체.
// 네이버 지도는 Client ID(NAVER_MAP_CLIENT_ID)를 서버에서 받아와 SDK 스크립트를
// 그때그때 불러와야 해서, 지도 초기화 전에 이 과정을 먼저 기다린다. Client ID가
// 아직 설정 안 됐거나(Render 환경변수 미등록) 네이버 쪽에 이 도메인이 아직 허용
// 목록에 없으면 로딩이 실패할 수 있는데, 그 경우에도 앱 자체는 계속 쓸 수 있도록
// 지도만 빈 화면으로 남기고 나머지 기능(경로 찾기 결과 목록, 위험신고 등)은 그대로 동작시킨다.
async function loadNaverSdk() {
  try {
    const config = await fetch(`${SAFETY_API_BASE}/api/config`).then(r => r.json());
    await NMap.loadSdk(config.naverMapClientId);
    return true;
  } catch (e) {
    console.warn("[naver-map] 지도 SDK 로딩 실패(지도 없이 계속 진행):", e);
    return false;
  }
}

function showMapUnavailableNotice() {
  ["map-home", "route-map"].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;' +
      'padding:16px;text-align:center;font-size:13px;color:#64748b;background:#f1f4f9;">' +
      '지도를 불러오지 못했어요. 잠시 후 앱을 다시 열어주세요.</div>';
  });
}

// 2026-09-25 추가: 네이버 지도의 인증 실패(window.navermap_authFailure)는 스크립트
// 로딩 자체는 성공한 뒤에도 뒤늦게 발생할 수 있다(admin/naver_map.py에서도 같은
// 이유로 fail()을 아무 때나 다시 호출해도 되게 짜여 있음). loadNaverSdk()가 이미
// true를 반환해서 지도 초기화까지 끝난 뒤라도, 이 훅이 불리면 똑같이 "지도를 쓸 수
// 없다"는 안내로 바꿔서 사용자가 깨진 지도를 보지 않게 한다.
NMap.onAuthFailure = function (err) {
  console.warn("[naver-map] 지도 초기화 이후 인증 실패 감지:", err);
  showMapUnavailableNotice();
};

// ---------- 앱 초기화 ----------
async function initApp() {
  await Promise.all([loadTopZones(), loadRecommendedPlaces(), loadDestinations()]);
  initTabs();
  initProfileEdit();
  initAdminRandomLocation();

  const mapReady = await loadNaverSdk();
  if (mapReady) {
    initHomeMap();
    initRouteMap();
  } else {
    showMapUnavailableNotice();
  }

  initMapResizeSafety();
  refreshLiveLocationUI(); // 홈 지도 초기화 시점엔 없던 안심경로 지도에도 현재 위치 마커를 바로 찍는다
  initRouteForm();
  initReportForm();
  initSaveTab();
  startLocationWatch(); // 이후로는 위치가 바뀔 때마다 두 지도의 내 위치 아이콘과 신고 위치 텍스트를 실시간으로 갱신
}

document.addEventListener("DOMContentLoaded", () => {
  loadProfile();
  if (state.profile.ageGroup) {
    enterApp(); // 이미 온보딩을 마친 적이 있으면 다시 거치지 않고 바로 앱으로
  } else {
    initOnboarding();
  }

  if (navigator.serviceWorker) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
});
