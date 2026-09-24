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
  routeResult: null, // 최근 /api/route 응답
  selectedRouteType: "safe",
  activeTab: "home",
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
    document.getElementById("onboarding").remove();
    document.getElementById("app").hidden = false;
    updateProfileChip();
    initApp();
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

function initHomeMap() {
  const center = state.location ? [state.location.lat, state.location.lng] : CHANGWON_CENTER;
  homeMap = L.map("map-home", { zoomControl: false }).setView(center, state.location ? 15 : 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(homeMap);

  recommendedLayer = L.layerGroup().addTo(homeMap);
  renderRecommendedPlaces();
  refreshLiveLocationUI();
}

const PLACE_STYLE = {
  library: { color: "#2563eb", emoji: "📚", label: "도서관" },
  park: { color: "#16a34a", emoji: "🌳", label: "공원" },
  police: { color: "#4f46e5", emoji: "🚓", label: "지구대·파출소" },
};

function renderRecommendedPlaces() {
  const places = state.recommendedPlaces || [];
  const withDist = places.map(p => ({
    ...p,
    dist: state.location ? haversineM(state.location.lat, state.location.lng, p.lat, p.lng) : null,
  }));

  if (recommendedLayer) {
    recommendedLayer.clearLayers();
    withDist.forEach(p => {
      const style = PLACE_STYLE[p.category] || { color: "#64748b", emoji: "📍", label: p.category };
      L.circleMarker([p.lat, p.lng], {
        radius: 6, color: style.color, fillColor: style.color, fillOpacity: 0.8, weight: 1.5,
      }).addTo(recommendedLayer).bindPopup(`<strong>${style.emoji} ${p.name}</strong><br/>${style.label}`);
    });
  }

  withDist.sort((a, b) => (a.dist ?? 1e9) - (b.dist ?? 1e9));
  const ul = document.getElementById("nearby-list");
  ul.innerHTML = "";
  withDist.slice(0, 3).forEach(item => {
    const style = PLACE_STYLE[item.category] || { color: "#64748b", emoji: "📍", label: item.category };
    const li = document.createElement("li");
    const distText = item.dist != null ? `${(item.dist / 1000).toFixed(1)}km` : "거리 확인 불가";
    li.innerHTML = `<span>${style.emoji} ${item.name} <small style="color:#94a3b8">· ${style.label}</small></span>` +
      `<span class="tag" style="background:${style.color}">${distText}</span>`;
    ul.appendChild(li);
  });
  if (withDist.length === 0) {
    ul.innerHTML = "<li>주변 추천시설 정보를 불러오지 못했어요.</li>";
  }
}

// 참고: 홈 화면 등급 배지(안전도 API 연동)는 사용자 피드백(2026-09-24)에 따라
// "위험성을 유발한다"는 이유로 홈 화면에서 제거했다. /api/safety 자체는 계속 살려두고
// Stage 3 안심경로(경로별 안전도 비교)에서 재사용할 예정이다.

// ---------- 실시간 위치 추적 (Stage 3 추가: 위치가 바뀔 때마다 내 위치 아이콘도 이동) ----------
let userMarkerHome = null;
let userMarkerRoute = null;
let locationWatchId = null;

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
    if (!userMarkerHome) {
      userMarkerHome = L.circleMarker(latlng, {
        radius: 8, color: "#1d4ed8", fillColor: "#1d4ed8", fillOpacity: 0.9, weight: 3,
      }).addTo(homeMap).bindPopup("내 위치(실시간)");
    } else {
      userMarkerHome.setLatLng(latlng);
    }
  }

  if (routeMap) {
    if (!userMarkerRoute) {
      userMarkerRoute = L.circleMarker(latlng, {
        radius: 8, color: "#1d4ed8", fillColor: "#60a5fa", fillOpacity: 0.95, weight: 3,
      }).addTo(routeMap).bindPopup("내 위치(실시간)");
    } else {
      userMarkerRoute.setLatLng(latlng);
    }
  }

  if (state.activeTab === "home") renderRecommendedPlaces();
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
};

const ROUTE_TYPE_COLOR = { fast: "#94a3b8", balanced: "#f97316", safe: "#16a34a" };

function initRouteMap() {
  routeMap = L.map("route-map", { zoomControl: false, dragging: true }).setView(
    state.location ? [state.location.lat, state.location.lng] : CHANGWON_CENTER, 13
  );
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(routeMap);
  routeLayers = L.layerGroup().addTo(routeMap);
}

async function loadDestinations() {
  const data = await fetch("data/destinations.json").then(r => r.json());
  state.destinations = data.places;
}

function searchDestinations(query, limit = 8) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const ageTag = state.profile.ageGroup === "child" ? "child" : state.profile.ageGroup === "senior" ? "senior" : null;
  return state.destinations
    .map(p => {
      const name = p.name.toLowerCase();
      let rank = name.startsWith(q) ? 0 : name.includes(q) ? 1 : null;
      if (rank === null) return null;
      if (ageTag && p.ageTag === ageTag) rank -= 0.5; // 연령대 맞춤 장소 우선 노출
      return { ...p, rank };
    })
    .filter(Boolean)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, limit);
}

function initRouteAutocomplete() {
  const input = document.getElementById("route-end");
  const list = document.getElementById("route-end-suggestions");
  const findBtn = document.getElementById("btn-find-route");

  function closeList() { list.hidden = true; list.innerHTML = ""; }

  function selectDestination(place) {
    state.routeDestination = place;
    input.value = place.name;
    closeList();
    findBtn.disabled = false;
  }

  input.addEventListener("input", () => {
    findBtn.disabled = true;
    state.routeDestination = null;
    const matches = searchDestinations(input.value);
    if (!matches.length) {
      list.innerHTML = input.value.trim() ? `<li class="suggestion-empty">일치하는 장소가 없어요</li>` : "";
      list.hidden = !input.value.trim();
      return;
    }
    list.innerHTML = "";
    matches.forEach(p => {
      const style = DEST_CATEGORY_STYLE[p.category] || { emoji: "📍", label: p.category };
      const li = document.createElement("li");
      li.innerHTML = `<span>${style.emoji} ${p.name}</span><small>${style.label}</small>`;
      li.addEventListener("mousedown", (e) => { e.preventDefault(); selectDestination(p); });
      list.appendChild(li);
    });
    list.hidden = false;
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
  routeLayers.clearLayers();

  L.circleMarker([data.start.lat, data.start.lng], { radius: 7, color: "#1d4ed8", fillColor: "#1d4ed8", fillOpacity: 0.95, weight: 3 })
    .addTo(routeLayers).bindPopup("출발지");
  L.circleMarker([data.end.lat, data.end.lng], { radius: 7, color: "#dc2626", fillColor: "#dc2626", fillOpacity: 0.95, weight: 3 })
    .addTo(routeLayers).bindPopup(state.routeDestination ? state.routeDestination.name : "도착지");

  const polylines = {};
  Object.entries(data.routes).forEach(([type, r]) => {
    const latlngs = r.path.map(p => [p.lat, p.lng]);
    polylines[type] = L.polyline(latlngs, {
      color: ROUTE_TYPE_COLOR[type], weight: type === state.selectedRouteType ? 6 : 3,
      opacity: type === state.selectedRouteType ? 0.95 : 0.45,
    }).addTo(routeLayers);
  });
  state._routePolylines = polylines;

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

  const selected = polylines[state.selectedRouteType];
  if (selected) routeMap.fitBounds(selected.getBounds(), { padding: [24, 24] });
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
  if (selected) routeMap.fitBounds(selected.getBounds(), { padding: [24, 24] });
}

function initRouteForm() {
  initRouteAutocomplete();

  document.getElementById("btn-find-route").addEventListener("click", async () => {
    const dest = state.routeDestination;
    if (!dest) {
      setRouteStatus("목록에서 도착지를 선택해주세요.", true);
      document.getElementById("route-end").focus();
      return;
    }
    if (!state.location) {
      setRouteStatus("현재 위치 정보가 없어 경로를 계산할 수 없어요. 위치 권한을 확인해주세요.", true);
      return;
    }

    const btn = document.getElementById("btn-find-route");
    btn.disabled = true;
    const originalLabel = btn.textContent;
    btn.textContent = "경로 계산 중…";
    setRouteStatus("출발지 주변 안전도를 분석해 3가지 경로를 계산하고 있어요…");
    document.getElementById("route-options").hidden = true;

    const ageGroup = state.profile.ageGroup || "adult";
    const url = `${SAFETY_API_BASE}/api/route?start_lat=${state.location.lat}&start_lng=${state.location.lng}` +
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
  });

  document.getElementById("route-options").addEventListener("click", (e) => {
    const opt = e.target.closest(".route-option");
    if (!opt || opt.disabled) return;
    highlightRouteType(opt.dataset.type);
  });
}

// ---------- 위험신고 ----------
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

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    // Stage 1: 로컬 목업 제출 (Stage 4/7에서 실제 백엔드 API로 교체)
    const report = {
      type: typeEl.value,
      desc: descEl.value.trim(),
      hasImage: !!imageEl.files.length,
      location: state.location,
      createdAt: new Date().toISOString(),
    };
    console.log("[mock submit] danger report", report);
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, 3200);
    form.reset();
    preview.hidden = true;
    submitBtn.disabled = true;
  });
}

// ---------- 앱 초기화 ----------
async function initApp() {
  await Promise.all([loadTopZones(), loadRecommendedPlaces(), loadDestinations()]);
  initTabs();
  initHomeMap();
  initRouteMap();
  refreshLiveLocationUI(); // 홈 지도 초기화 시점엔 없던 안심경로 지도에도 현재 위치 마커를 바로 찍는다
  initRouteForm();
  initReportForm();
  startLocationWatch(); // 이후로는 위치가 바뀔 때마다 두 지도의 내 위치 아이콘과 신고 위치 텍스트를 실시간으로 갱신
}

document.addEventListener("DOMContentLoaded", () => {
  loadProfile();
  initOnboarding();

  if (navigator.serviceWorker) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
});
