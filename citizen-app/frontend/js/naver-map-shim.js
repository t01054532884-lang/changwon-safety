/* 창원 안심길 — 지도 표시 엔진: Leaflet+OpenStreetMap → NAVER 지도 JS SDK 교체 (2026-09-26)
 *
 * 왜 이 파일이 필요한가:
 * app.js의 지도 관련 코드는 전부 Leaflet API(L.map/L.marker/L.polyline/L.divIcon 등)를
 * 그대로 호출하는 형태로 짜여 있었다. 이 SDK 자체를 통째로 새로 배우면서 매 호출을
 * 다시 짜면 실수가 나기 쉬우므로, 대신 "NMap"이라는 이름으로 Leaflet과 최대한 같은
 * 모양(같은 메서드 이름, 같은 인자 형태)의 얇은 래퍼를 만들고, app.js 쪽은
 * "L." → "NMap."으로만 바꿔서 그대로 재사용한다. 실제 지도 그리기는 이 파일 안에서만
 * naver.maps.* 객체로 처리한다.
 *
 * 여기서 쓰는 naver.maps.* 패턴(Marker의 icon:{content,size,anchor}, Polyline, Circle,
 * LatLngBounds, InfoWindow, setMap(null/map) 등)은 이 저장소의 admin/naver_map.py에서
 * 이미 실제 배포 중인 관리자 웹 지도가 쓰고 있는 것과 최대한 동일하게 맞췄다 — 즉
 * "새로 짠 코드"가 아니라 "이미 검증된 패턴을 그대로 옮긴 것"이라는 뜻이다.
 *
 * 다만 아래 두 가지는 이 샌드박스 환경(네이버 지도 서버에 네트워크 접근 불가)에서
 * 실제로 실행해서 확인할 방법이 없었다 — 실제 기기에서 확인이 꼭 필요하다:
 *   1) naver.maps.Circle (홈 지도의 은은한 "번짐" 효과에만 사용, 안 보여도 핵심 기능에는
 *      영향 없음 — admin 지도는 Rectangle만 쓰고 Circle은 쓴 적이 없어서 유일하게
 *      완전히 검증되지 않은 부분)
 *   2) 지도 크기 재계산(invalidateSize 대응) — map.refresh()가 안 되면
 *      naver.maps.Event.trigger(map,"resize")로 대체 시도하도록 방어적으로 짰다.
 */

const NMap = {};

// ---------- SDK 스크립트 로딩 ----------
NMap._sdkPromise = null;
NMap.loadSdk = function (clientId) {
  if (NMap._sdkPromise) return NMap._sdkPromise;
  NMap._sdkPromise = new Promise((resolve, reject) => {
    if (window.naver && window.naver.maps) {
      resolve();
      return;
    }
    if (!clientId) {
      reject(new Error("네이버 지도 Client ID가 아직 설정되지 않았습니다."));
      return;
    }
    const script = document.createElement("script");
    script.src = "https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=" + encodeURIComponent(clientId);
    script.async = true;
    script.onload = () => {
      if (window.naver && window.naver.maps) resolve();
      else reject(new Error("네이버 지도 SDK 응답이 올바르지 않습니다."));
    };
    script.onerror = () => reject(new Error("네이버 지도 SDK를 불러오지 못했습니다."));
    document.head.appendChild(script);
    setTimeout(() => {
      if (!(window.naver && window.naver.maps)) {
        reject(new Error("네이버 지도 연결 시간이 초과되었습니다. API 서비스 URL 등록 상태를 확인해주세요."));
      }
    }, 10000);
  });
  return NMap._sdkPromise;
};

// ---------- 공통 오버레이(마커/원/폴리라인) 베이스 ----------
// Leaflet의 "레이어 그룹에 addTo하면 그 그룹이 지도에 붙을 때 같이 붙는다"는 동작을
// 그대로 흉내낸다. target이 layerGroup이면 그룹에 등록하고, target이 지도 래퍼(NMap.map()의
// 반환값)이면 바로 지도에 올린다.
function createOverlayBase() {
  return {
    _mapWrapper: null,
    _real: null,
    _popupHtml: null,
    _popupBound: false,
    addTo(target) {
      if (target && typeof target._register === "function") {
        target._register(this);
      } else if (target) {
        this._attach(target);
      }
      return this;
    },
    _attach(mapWrapper) {
      this._mapWrapper = mapWrapper;
      if (this._real && mapWrapper && mapWrapper._naverMap) {
        this._real.setMap(mapWrapper._naverMap);
      }
      this._ensurePopupBound();
    },
    _detach() {
      if (this._real) this._real.setMap(null);
      this._mapWrapper = null;
    },
    bindPopup(html) {
      this._popupHtml = html;
      this._ensurePopupBound();
      return this;
    },
    _ensurePopupBound() {
      if (this._popupBound || !this._real || !window.naver) return;
      this._popupBound = true;
      naver.maps.Event.addListener(this._real, "click", () => {
        if (!this._mapWrapper || !this._mapWrapper._infoWindow || !this._popupHtml) return;
        this._mapWrapper._infoWindow.setContent(
          '<div style="padding:5px 9px;font-size:13px;line-height:1.55;max-width:230px">' + this._popupHtml + "</div>"
        );
        this._mapWrapper._infoWindow.open(this._mapWrapper._naverMap, this._real);
      });
    },
  };
}

function iconSpecToNaverIcon(spec) {
  if (!spec) return undefined;
  return {
    content: spec.html,
    size: new naver.maps.Size(spec.iconSize[0], spec.iconSize[1]),
    anchor: new naver.maps.Point(spec.iconAnchor[0], spec.iconAnchor[1]),
  };
}

// ---------- 지도 ----------
NMap.map = function (elementId, opts = {}) {
  const wrapper = {
    _elementId: elementId,
    _naverMap: null,
    _infoWindow: null,
    _zoomControl: !!opts.zoomControl,
    setView(center, zoom) {
      if (!this._naverMap) {
        this._naverMap = new naver.maps.Map(this._elementId, {
          center: new naver.maps.LatLng(center[0], center[1]),
          zoom: zoom,
          zoomControl: this._zoomControl,
        });
        this._infoWindow = new naver.maps.InfoWindow({
          borderWidth: 0,
          backgroundColor: "transparent",
          anchorSize: new naver.maps.Size(10, 8),
        });
      } else {
        this._naverMap.setCenter(new naver.maps.LatLng(center[0], center[1]));
        this._naverMap.setZoom(zoom);
      }
      return this;
    },
    invalidateSize() {
      if (!this._naverMap) return this;
      try {
        if (typeof this._naverMap.refresh === "function") {
          this._naverMap.refresh(true);
        } else if (window.naver && naver.maps && naver.maps.Event) {
          naver.maps.Event.trigger(this._naverMap, "resize");
        }
      } catch (e) {
        // 지도 크기 재계산이 실패해도 앱이 멈추면 안 되므로 무시한다.
      }
      return this;
    },
    fitBounds(bounds, fitOpts = {}) {
      if (!this._naverMap || !bounds) return this;
      const padding = fitOpts.padding || [24, 24];
      const margin = { top: padding[1], bottom: padding[1], left: padding[0], right: padding[0] };
      try {
        this._naverMap.fitBounds(bounds, margin);
      } catch (e) {
        try {
          this._naverMap.fitBounds(bounds);
        } catch (e2) {
          // 무시 — 화면이 딱 안 맞아도 경로 자체는 이미 그려져 있음
        }
      }
      return this;
    },
  };
  return wrapper;
};

// Leaflet은 별도 타일 레이어를 지도에 추가해야 했지만, 네이버 지도는 Map 생성 시
// 자체 지도 타일을 이미 그려주므로 이 함수는 아무 것도 하지 않는 자리표시자다.
NMap.tileLayer = function () {
  return { addTo() { return this; } };
};

// ---------- 레이어 그룹(마커 묶음 관리) ----------
NMap.layerGroup = function () {
  const group = {
    _items: [],
    _mapWrapper: null,
    addTo(mapWrapper) {
      this._mapWrapper = mapWrapper;
      return this;
    },
    _register(overlay) {
      this._items.push(overlay);
      if (this._mapWrapper) overlay._attach(this._mapWrapper);
    },
    clearLayers() {
      this._items.forEach((o) => o._detach());
      this._items = [];
    },
  };
  return group;
};

// ---------- divIcon (Leaflet의 커스텀 HTML 아이콘 스펙과 동일한 모양으로 반환) ----------
NMap.divIcon = function (spec) {
  return { html: spec.html, iconSize: spec.iconSize, iconAnchor: spec.iconAnchor };
};

// ---------- 마커 ----------
NMap.marker = function (latlng, opts = {}) {
  const overlay = createOverlayBase();
  overlay._real = new naver.maps.Marker({
    position: new naver.maps.LatLng(latlng[0], latlng[1]),
    map: null,
    icon: iconSpecToNaverIcon(opts.icon),
    clickable: opts.interactive !== false,
  });
  overlay.setLatLng = function (ll) {
    this._real.setPosition(new naver.maps.LatLng(ll[0], ll[1]));
    return this;
  };
  overlay.setIcon = function (spec) {
    this._real.setIcon(iconSpecToNaverIcon(spec));
    return this;
  };
  return overlay;
};

// ---------- 원형 마커(픽셀 고정 크기 — 내 위치 점, 출발/도착 점) ----------
// Leaflet의 L.circleMarker는 반경이 "화면 픽셀" 기준이라 확대/축소해도 크기가 그대로다.
// naver.maps.Circle은 "실제 거리(m)" 기준이라 다르게 동작하므로, 대신 SVG를 그려넣은
// 마커 아이콘으로 흉내낸다(admin/naver_map.py의 start-pin/end-pin과 같은 방식).
NMap.circleMarker = function (latlng, opts = {}) {
  const radius = opts.radius || 6;
  const strokeW = opts.weight != null ? opts.weight : 2;
  const size = radius * 2 + strokeW * 2 + 2;
  const half = size / 2;
  const html =
    `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">` +
    `<circle cx="${half}" cy="${half}" r="${radius}" fill="${opts.fillColor || opts.color || "#1d4ed8"}" ` +
    `fill-opacity="${opts.fillOpacity != null ? opts.fillOpacity : 1}" ` +
    `stroke="${opts.color || "#1d4ed8"}" stroke-width="${strokeW}" /></svg>`;

  const overlay = createOverlayBase();
  overlay._real = new naver.maps.Marker({
    position: new naver.maps.LatLng(latlng[0], latlng[1]),
    map: null,
    icon: { content: html, size: new naver.maps.Size(size, size), anchor: new naver.maps.Point(half, half) },
    clickable: opts.interactive !== false,
  });
  overlay.setLatLng = function (ll) {
    this._real.setPosition(new naver.maps.LatLng(ll[0], ll[1]));
    return this;
  };
  return overlay;
};

// ---------- 원(실거리 반경 — 홈 지도의 은은한 "번짐" 표시) ----------
NMap.circle = function (latlng, opts = {}) {
  const overlay = createOverlayBase();
  try {
    overlay._real = new naver.maps.Circle({
      map: null,
      center: new naver.maps.LatLng(latlng[0], latlng[1]),
      radius: opts.radius,
      strokeWeight: opts.stroke === false ? 0 : opts.weight || 1,
      strokeOpacity: opts.stroke === false ? 0 : 1,
      fillColor: opts.fillColor,
      fillOpacity: opts.fillOpacity != null ? opts.fillOpacity : 0.2,
      clickable: !!opts.interactive,
    });
  } catch (e) {
    // naver.maps.Circle이 예상과 다르게 동작해도(이 부분만 미검증) 앱이 죽지 않게 한다 —
    // 이 원은 순전히 장식용(안전 영향권 은은한 번짐)이라 안 보여도 기능엔 지장 없음.
    overlay._real = { setMap() {} };
  }
  return overlay;
};

// ---------- 폴리라인(경로 선) ----------
// setStyle/bringToFront은 naver.maps.Polyline에 옵션을 직접 바꾸는 메서드가 있는지
// 확인할 방법이 없어서, 대신 "지우고 새로 그리기"로 안전하게 구현했다(생성/setMap(null)은
// admin/naver_map.py에서 이미 검증된 패턴이라 이 방식이 가장 위험이 낮다).
NMap.polyline = function (latlngs, opts = {}) {
  const overlay = createOverlayBase();
  overlay._path = latlngs.map((p) => new naver.maps.LatLng(p[0], p[1]));
  overlay._color = opts.color || "#1d4ed8";
  overlay._weight = opts.weight != null ? opts.weight : 4;
  overlay._opacity = opts.opacity != null ? opts.opacity : 0.9;
  overlay._zIndex = 100;

  function buildReal(mapInstance) {
    return new naver.maps.Polyline({
      map: mapInstance || null,
      path: overlay._path,
      strokeColor: overlay._color,
      strokeWeight: overlay._weight,
      strokeOpacity: overlay._opacity,
      strokeLineCap: "round",
      strokeLineJoin: "round",
      zIndex: overlay._zIndex,
    });
  }
  overlay._real = buildReal(null);

  overlay._redraw = function () {
    const wasOnMap = this._mapWrapper && this._mapWrapper._naverMap;
    if (this._real) this._real.setMap(null);
    this._real = buildReal(wasOnMap ? this._mapWrapper._naverMap : null);
  };
  overlay.setStyle = function (style) {
    if (style.weight != null) this._weight = style.weight;
    if (style.opacity != null) this._opacity = style.opacity;
    this._redraw();
    return this;
  };
  overlay.bringToFront = function () {
    NMap._zCounter = (NMap._zCounter || 200) + 1;
    this._zIndex = NMap._zCounter;
    this._redraw();
    return this;
  };
  overlay.getBounds = function () {
    const bounds = new naver.maps.LatLngBounds();
    this._path.forEach((p) => bounds.extend(p));
    return bounds;
  };
  return overlay;
};
