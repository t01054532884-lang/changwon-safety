// 2026-09-26: 지도 표시 엔진을 Leaflet+OpenStreetMap → 네이버 지도 JS SDK로 교체하면서
// 캐시 이름을 올려 예전 v3 캐시(leaflet 파일 포함)를 정리한다(activate 핸들러가 처리).
const CACHE_NAME = "anshim-gil-v4";
const APP_SHELL = [
  "./",
  "./index.html",
  "./css/style.css",
  "./js/naver-map-shim.js",
  "./js/app.js",
  "./manifest.json",
  "./data/child_top10.geojson",
  "./data/elderly_top10.geojson",
  "./data/recommended_places.json",
  "./data/destinations.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 2026-09-24 변경: 예전엔 "캐시 우선"이라서 배포 후에도 브라우저가 예전 화면을
// 계속 보여주는 문제가 있었다(sw.js 자체가 바뀌지 않으면 새 버전 감지도 안 됨).
// 이제는 "네트워크 우선"으로 바꿔서, 온라인이면 항상 최신 파일을 받아오고
// (받아온 걸 캐시에도 갱신) 오프라인일 때만 마지막으로 저장된 캐시를 대신 보여준다.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const resClone = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, resClone)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
