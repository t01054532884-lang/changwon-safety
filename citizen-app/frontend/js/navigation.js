// =====================================================================
// 안심경로 내비 안내 (2026-09-27 추가)
// ---------------------------------------------------------------------
// - "🧭 안내 시작": 남은 거리·시간 실시간 갱신, 지나온 길 연한 회색, 경로에서 50m 이상
//   벗어나면 경고, 도착하면 알림, 안내 중 화면 꺼짐 방지(Wake Lock)
// - "▶ 모의 주행": 주소 끝에 ?demo=1 을 붙여 들어왔을 때만 보인다(발표 시연용).
//   화살표가 경로를 따라 자동으로 움직인다. "↗ 경로 이탈 테스트"로 이탈 경고도 시연 가능.
//
// app.js는 건드리지 않고, app.js의 함수 3개(refreshLiveLocationUI, renderRouteResult,
// highlightRouteType)를 "원래 동작 그대로 실행한 뒤 안내 계산만 덧붙이는" 방식으로 감쌌다.
// 되돌리려면 index.html의 <script src="js/navigation.js"> 한 줄만 지우면 된다.
// =====================================================================
(function () {
  "use strict";

  if (typeof refreshLiveLocationUI !== "function" || typeof renderRouteResult !== "function") {
    console.warn("[nav] app.js 함수를 찾지 못해 내비 안내를 켜지 않습니다.");
    return;
  }

  const IS_DEMO = new URLSearchParams(window.location.search).get("demo") === "1";
  const OFF_ROUTE_M = 50;        // 이만큼 벗어나면 이탈 경고
  const ARRIVE_M = 25;           // 남은 거리가 이 안쪽이면 도착
  const SIM_TICK_MS = 300;       // 모의 주행 한 걸음 간격
  const SIM_TARGET_SEC = 45;     // 모의 주행 전체 소요 시간(대략)

  const nav = {
    active: false,
    sim: null,                   // { timer, dist, total, offTicks }
    simTick: false,
    simPos: null,                // 마지막 모의 위치
    simHold: false,              // 모의 주행이 도착으로 끝난 뒤 "닫기" 전까지 모의 위치 유지
    realLocation: null,
    passedLine: null,
    offCount: 0,
    wakeLock: null,
  };

  // ---------- 스타일 (style.css를 건드리지 않도록 여기서 넣는다) ----------
  const css = `
    .nav-actions { display: flex; gap: 8px; margin: 0; }
    .nav-actions button { flex: 1; margin: 0; }
    .nav-card { margin: 10px 16px 0; padding: 12px 14px; border-radius: 14px; background: #eff4ff;
      border: 1.5px solid #1d4ed8; }
    .nav-card-head { display: flex; justify-content: space-between; align-items: center;
      font-weight: 800; color: #1d4ed8; font-size: 15px; }
    .nav-card-head button { border: 0; background: #fff; color: #334155; font-weight: 700;
      border-radius: 10px; padding: 8px 12px; font-size: 13px; cursor: pointer; }
    .nav-remaining { margin-top: 6px; font-size: 20px; font-weight: 800; color: #0f172a; }
    .nav-alert { margin-top: 8px; padding: 8px 10px; border-radius: 10px; font-size: 14px;
      font-weight: 700; line-height: 1.45; }
    .nav-alert.is-warn { background: #fef3c7; color: #92400e; }
    .nav-alert.is-done { background: #dcfce7; color: #166534; }
    .nav-demo-row { margin-top: 8px; }
    .nav-demo-row button { width: 100%; border: 1px dashed #94a3b8; background: #fff;
      border-radius: 10px; padding: 8px; font-size: 13px; font-weight: 700; color: #475569; }
  `;
  const styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  // ---------- 화면 요소 만들기 ----------
  const options = document.getElementById("route-options");
  const routeMapEl = document.getElementById("route-map");
  if (!options || !routeMapEl) return;

  const actions = document.createElement("div");
  actions.className = "nav-actions";
  actions.innerHTML =
    `<button type="button" class="btn-primary" id="btn-nav-start">🧭 안내 시작</button>` +
    (IS_DEMO ? `<button type="button" class="btn-secondary" id="btn-nav-sim">▶ 모의 주행</button>` : "");
  options.insertBefore(actions, options.firstChild); // 경로 옵션 목록 맨 위에 둔다

  const card = document.createElement("div");
  card.className = "nav-card";
  card.id = "nav-card";
  card.hidden = true;
  card.innerHTML =
    `<div class="nav-card-head"><span id="nav-mode">🧭 안내 중</span>` +
    `<button type="button" id="btn-nav-stop">■ 안내 종료</button></div>` +
    `<div class="nav-remaining" id="nav-remaining">남은 거리 계산 중…</div>` +
    `<div class="nav-alert" id="nav-alert" hidden></div>` +
    (IS_DEMO ? `<div class="nav-demo-row" id="nav-demo-row" hidden>` +
      `<button type="button" id="btn-nav-offroute">↗ 경로 이탈 테스트 (시연용)</button></div>` : "");
  routeMapEl.insertAdjacentElement("afterend", card);

  const el = (id) => document.getElementById(id);

  // ---------- 경로 계산 도우미 ----------
  function selectedRoute() {
    const routes = state.routeResult && state.routeResult.routes;
    const r = routes && routes[state.selectedRouteType];
    return r && Array.isArray(r.path) && r.path.length >= 2 ? r : null;
  }

  // 위도·경도를 미터 단위 평면 좌표로 (짧은 거리라 이 근사로 충분)
  function toXY(lat, lng, lat0) {
    return { x: lng * 111320 * Math.cos(lat0 * Math.PI / 180), y: lat * 110540 };
  }

  function buildGeometry(route) {
    const lat0 = route.path[0].lat;
    const pts = route.path.map(p => toXY(p.lat, p.lng, lat0));
    const cum = [0];
    for (let i = 1; i < pts.length; i++) {
      cum.push(cum[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y));
    }
    return { lat0, pts, cum, total: cum[cum.length - 1] };
  }

  // 내 위치를 경로 위에 투영: 경로에서 얼마나 떨어졌는지(off), 출발부터 몇 m 왔는지(along)
  function project(geo, lat, lng) {
    const p = toXY(lat, lng, geo.lat0);
    let best = { off: Infinity, along: 0, seg: 0, t: 0 };
    for (let i = 0; i < geo.pts.length - 1; i++) {
      const a = geo.pts[i], b = geo.pts[i + 1];
      const dx = b.x - a.x, dy = b.y - a.y;
      const len2 = dx * dx + dy * dy;
      let t = len2 > 0 ? ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2 : 0;
      t = Math.max(0, Math.min(1, t));
      const off = Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
      if (off < best.off) best = { off, along: geo.cum[i] + t * Math.sqrt(len2), seg: i, t };
    }
    return best;
  }

  // 출발부터 d(m) 지점의 위도·경도 (모의 주행용)
  function pointAt(route, geo, d) {
    const path = route.path;
    if (d <= 0) return { lat: path[0].lat, lng: path[0].lng, seg: 0 };
    for (let i = 0; i < path.length - 1; i++) {
      const segLen = geo.cum[i + 1] - geo.cum[i];
      if (d <= geo.cum[i + 1] || i === path.length - 2) {
        const t = segLen > 0 ? Math.min(1, (d - geo.cum[i]) / segLen) : 0;
        return {
          lat: path[i].lat + (path[i + 1].lat - path[i].lat) * t,
          lng: path[i].lng + (path[i + 1].lng - path[i].lng) * t,
          seg: i,
        };
      }
    }
    const last = path[path.length - 1];
    return { lat: last.lat, lng: last.lng, seg: path.length - 2 };
  }

  function formatDist(m) {
    return m >= 1000 ? `${(m / 1000).toFixed(2)}km` : `${Math.max(0, Math.round(m / 10) * 10)}m`;
  }

  // ---------- 지나온 길 그리기 ----------
  function clearPassedLine() {
    if (nav.passedLine) {
      try { nav.passedLine._detach(); } catch (e) {}
      nav.passedLine = null;
    }
  }

  function drawPassedLine(route, proj) {
    clearPassedLine();
    if (!routeMap || typeof NMap === "undefined" || proj.along < 3) return;
    const latlngs = route.path.slice(0, proj.seg + 1).map(p => [p.lat, p.lng]);
    const a = route.path[proj.seg], b = route.path[proj.seg + 1];
    latlngs.push([a.lat + (b.lat - a.lat) * proj.t, a.lng + (b.lng - a.lng) * proj.t]);
    try {
      nav.passedLine = NMap.polyline(latlngs, { color: "#cbd5e1", weight: 8, opacity: 0.95 }).addTo(routeMap);
      nav.passedLine.bringToFront();
    } catch (e) {
      nav.passedLine = null;
    }
  }

  // ---------- 알림 표시 ----------
  function showAlert(text, kind) {
    const box = el("nav-alert");
    if (!box) return;
    box.textContent = text || "";
    box.hidden = !text;
    box.classList.toggle("is-warn", kind === "warn");
    box.classList.toggle("is-done", kind === "done");
  }

  // ---------- 매 위치 갱신마다 안내 계산 ----------
  function updateGuidance() {
    if (!nav.active || !state.location) return;
    const route = selectedRoute();
    if (!route) return;
    const geo = buildGeometry(route);
    const proj = project(geo, state.location.lat, state.location.lng);
    const remaining = Math.max(0, geo.total - proj.along);
    const minutes = route.duration_min && geo.total > 0
      ? Math.max(1, Math.ceil(route.duration_min * remaining / geo.total))
      : Math.max(1, Math.ceil(remaining / 67)); // 분당 약 67m(시속 4km)

    drawPassedLine(route, proj);

    if (remaining <= ARRIVE_M && proj.off <= OFF_ROUTE_M) {
      el("nav-remaining").textContent = "남은 거리 0m";
      finish("🎉 목적지에 도착했어요! 오늘도 안전하게 도착하셨어요.");
      return;
    }

    el("nav-remaining").textContent = `남은 거리 ${formatDist(remaining)} · 약 ${minutes}분`;

    if (proj.off > OFF_ROUTE_M) {
      nav.offCount += 1;
      // GPS가 한 번 튀는 건 무시하고, 두 번 연속 벗어났을 때만 경고
      if (nav.offCount >= 2 || nav.sim) {
        if (proj.off > 1000) {
          showAlert(`⚠️ 경로에서 약 ${formatDist(proj.off)} 떨어져 있어요. 출발지 근처에서 안내를 시작해 주세요.`, "warn");
        } else {
          if (!el("nav-alert").classList.contains("is-warn") && navigator.vibrate) navigator.vibrate(200);
          showAlert(`⚠️ 경로를 벗어났어요 · 경로까지 약 ${formatDist(proj.off)}`, "warn");
        }
      }
    } else {
      nav.offCount = 0;
      showAlert("", null);
    }
  }

  // ---------- 화면 꺼짐 방지 ----------
  async function requestWakeLock() {
    try {
      if ("wakeLock" in navigator && !nav.wakeLock) {
        nav.wakeLock = await navigator.wakeLock.request("screen");
        nav.wakeLock.addEventListener("release", () => { nav.wakeLock = null; });
      }
    } catch (e) { /* 지원 안 하는 기기면 그냥 넘어감 */ }
  }
  function releaseWakeLock() {
    try { if (nav.wakeLock) nav.wakeLock.release(); } catch (e) {}
    nav.wakeLock = null;
  }
  document.addEventListener("visibilitychange", () => {
    if (nav.active && document.visibilityState === "visible") requestWakeLock();
  });

  // ---------- 시작 / 종료 ----------
  function start(isSim) {
    const route = selectedRoute();
    if (!route) return;
    stopSim(false);
    nav.active = true;
    nav.offCount = 0;
    card.hidden = false;
    actions.hidden = true;
    el("nav-mode").textContent = isSim ? "▶ 모의 주행 중" : "🧭 안내 중";
    el("btn-nav-stop").textContent = "■ 안내 종료";
    showAlert("", null);
    requestWakeLock();

    if (isSim) {
      startSim(route);
    } else if (!state.location) {
      el("nav-remaining").textContent = "현재 위치를 확인하는 중…";
    } else {
      if (routeMap && typeof isNearSelectedRoute === "function" && isNearSelectedRoute()) {
        routeMap.setView([state.location.lat, state.location.lng], 17);
      }
      updateGuidance();
    }
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function finish(message) {
    if (nav.sim) nav.simHold = true; // 시연 중이면 도착 지점을 "닫기" 전까지 그대로 보여준다
    stopSim(false);
    nav.active = false;
    releaseWakeLock();
    el("nav-mode").textContent = "✅ 안내 완료";
    el("btn-nav-stop").textContent = "닫기";
    showAlert(message, "done");
    if (navigator.vibrate) navigator.vibrate([150, 80, 150]);
  }

  function stop() {
    stopSim(true);
    if (nav.simHold) {
      nav.simHold = false;
      if (nav.realLocation) {
        state.location = nav.realLocation;
        nav.realLocation = null;
        try { refreshLiveLocationUI(); } catch (e) {}
      }
    }
    nav.active = false;
    releaseWakeLock();
    clearPassedLine();
    card.hidden = true;
    actions.hidden = false;
    showAlert("", null);
  }

  // ---------- 모의 주행 ----------
  function startSim(route) {
    const geo = buildGeometry(route);
    if (!nav.simHold) nav.realLocation = state.location ? { ...state.location } : null;
    nav.simHold = false;
    nav.sim = {
      dist: 0,
      step: Math.max(4, geo.total / (SIM_TARGET_SEC * 1000 / SIM_TICK_MS)),
      offTicks: 0,
      timer: null,
    };
    const demoRow = el("nav-demo-row");
    if (demoRow) demoRow.hidden = false;
    if (routeMap) {
      const p0 = route.path[0];
      routeMap.setView([p0.lat, p0.lng], 17);
    }
    simStep();
    nav.sim.timer = setInterval(simStep, SIM_TICK_MS);
  }

  function simStep() {
    if (!nav.sim) return;
    const route = selectedRoute();
    if (!route) { stop(); return; }
    const geo = buildGeometry(route);
    nav.sim.dist = Math.min(geo.total, nav.sim.dist + (nav.sim.offTicks > 0 ? 0 : nav.sim.step));
    let pos = pointAt(route, geo, nav.sim.dist);

    // "경로 이탈 테스트": 진행 방향의 옆쪽으로 약 80m 비켜난 위치를 잠깐 보여준다
    if (nav.sim.offTicks > 0) {
      nav.sim.offTicks -= 1;
      const a = route.path[pos.seg], b = route.path[pos.seg + 1];
      const pa = toXY(a.lat, a.lng, geo.lat0), pb = toXY(b.lat, b.lng, geo.lat0);
      const len = Math.hypot(pb.x - pa.x, pb.y - pa.y) || 1;
      const nx = -(pb.y - pa.y) / len, ny = (pb.x - pa.x) / len; // 진행 방향의 왼쪽 수직
      pos = {
        lat: pos.lat + (ny * 80) / 110540,
        lng: pos.lng + (nx * 80) / (111320 * Math.cos(geo.lat0 * Math.PI / 180)),
        seg: pos.seg,
      };
    }

    nav.simTick = true;
    nav.simPos = { lat: pos.lat, lng: pos.lng };
    state.location = { ...nav.simPos };
    try { refreshLiveLocationUI(); } finally { nav.simTick = false; }
  }

  function stopSim(restoreReal) {
    if (!nav.sim) return;
    clearInterval(nav.sim.timer);
    nav.sim = null;
    const demoRow = el("nav-demo-row");
    if (demoRow) demoRow.hidden = true;
    if (restoreReal && nav.realLocation) {
      state.location = nav.realLocation;
      nav.realLocation = null;
      try { refreshLiveLocationUI(); } catch (e) {}
    }
  }

  // ---------- 버튼 연결 ----------
  el("btn-nav-start").addEventListener("click", () => start(false));
  if (el("btn-nav-sim")) el("btn-nav-sim").addEventListener("click", () => start(true));
  el("btn-nav-stop").addEventListener("click", stop);
  if (el("btn-nav-offroute")) {
    el("btn-nav-offroute").addEventListener("click", () => {
      if (nav.sim) nav.sim.offTicks = 10; // 약 3초 동안 경로 밖으로
    });
  }

  // ---------- app.js 함수 감싸기 (원래 동작은 그대로 먼저 실행) ----------
  const originalRefresh = refreshLiveLocationUI;
  window.refreshLiveLocationUI = function () {
    // 모의 주행 중에 실제 GPS가 들어오면: 실제 위치는 기억만 해두고 모의 위치를 유지
    if ((nav.sim || nav.simHold) && !nav.simTick && state.location) {
      nav.realLocation = { ...state.location };
      if (nav.simPos) state.location = { ...nav.simPos };
      return;
    }
    const result = originalRefresh.apply(this, arguments);
    try { updateGuidance(); } catch (e) { console.error("[nav] 안내 계산 실패:", e); }
    return result;
  };

  const originalRender = renderRouteResult;
  window.renderRouteResult = function () {
    stop(); // 새 경로를 찾으면 진행 중이던 안내는 끝낸다
    return originalRender.apply(this, arguments);
  };

  if (typeof highlightRouteType === "function") {
    const originalHighlight = highlightRouteType;
    window.highlightRouteType = function () {
      const result = originalHighlight.apply(this, arguments);
      try { if (nav.active) updateGuidance(); } catch (e) {}
      return result;
    };
  }

  console.log("[nav] 내비 안내 준비 완료" + (IS_DEMO ? " (시연 모드: 모의 주행 사용 가능)" : ""));
})();
