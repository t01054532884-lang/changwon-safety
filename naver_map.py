"""NAVER Maps JavaScript renderer for the Streamlit safety map."""

from __future__ import annotations

import base64
import json
from urllib.parse import quote


def png_data_url(image_bytes: bytes | None) -> str | None:
    if not image_bytes:
        return None
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_naver_map_html(client_id: str, payload: dict) -> str:
    """Return a self-contained NAVER map with all analysis overlays."""
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    safe_client_id = quote(client_id, safe="")
    template = r"""
<style>
    #changwon-naver-shell{position:relative;width:100%;height:820px;overflow:hidden;background:#eef2f7;font-family:Pretendard,"Noto Sans KR",sans-serif}
    #changwon-naver-map{width:100%;height:100%}.panel{position:absolute;z-index:1000;background:rgba(255,255,255,.96);border:1px solid #cbd5e1;border-radius:12px;box-shadow:0 4px 18px rgba(15,23,42,.18);color:#0f172a}
    #layers{top:12px;right:12px;width:224px;padding:11px 12px}.panel-title{font-size:14px;font-weight:900;margin-bottom:7px}.layer{display:flex;align-items:center;gap:7px;padding:4px 0;font-size:12px;font-weight:700}.layer input{width:16px;height:16px;accent-color:#16a34a}.legend{left:12px;bottom:28px;min-width:185px;padding:10px 12px;font-size:12px;font-weight:700}.legend-row{display:flex;align-items:center;gap:8px;margin:5px 0}.dot{width:13px;height:13px;border-radius:50%;display:inline-block}.risk{background:#ef4444;border:2px solid #7f1d1d;box-shadow:0 0 6px #ef4444}.route{width:22px;border-top:5px solid #2563eb}.boundary{width:22px;border-top:4px solid #312e81}.triangle{color:#16a34a;font-size:21px;line-height:13px}.naver-badge{position:absolute;z-index:999;left:12px;top:12px;padding:7px 10px;border-radius:8px;background:rgba(3,199,90,.94);color:white;font-size:12px;font-weight:900;box-shadow:0 2px 8px rgba(0,0,0,.18)}
    .safe-triangle{width:29px;height:27px;filter:drop-shadow(0 2px 2px rgba(20,83,45,.65))}.facility-marker{display:flex;align-items:center;justify-content:center;min-width:23px;height:23px;padding:0 4px;border-radius:14px;border:2px solid #fff;color:#fff;font-size:10px;font-weight:900;box-shadow:0 1px 5px rgba(0,0,0,.35)}.cctv{background:#dc2626}.light{background:#ca8a04}.wifi{background:#0284c7}.start-pin,.end-pin{display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;border:3px solid white;color:white;font-size:12px;font-weight:900;box-shadow:0 2px 7px rgba(0,0,0,.38)}.start-pin{background:#2563eb}.end-pin{background:#dc2626}.info{padding:10px 12px;max-width:280px;line-height:1.55;font-size:12px}.info b{font-size:13px}.error{position:absolute;inset:0;display:none;z-index:2000;align-items:center;justify-content:center;background:#f8fafc;color:#b91c1c;font-weight:800;text-align:center;padding:30px}
    @media(max-width:700px){#layers{top:48px;right:8px;width:185px;padding:8px 10px}.layer{font-size:11px;padding:3px 0}.legend{left:8px;bottom:22px;min-width:160px;padding:8px 10px}.naver-badge{left:8px;top:8px}}
  </style>
<div id="changwon-naver-shell">
  <div id="changwon-naver-map"></div>
  <div class="naver-badge">NAVER 지도 · 창원 안전경로</div>
  <div id="layers" class="panel"><div class="panel-title">지도 레이어</div><div id="layer-items"></div></div>
  <div class="legend panel">
    <div class="panel-title">안전 분석 표시</div>
    <div class="legend-row"><span class="dot risk"></span>범죄위험 밀도·고위험 격자</div>
    <div class="legend-row"><span class="triangle">△</span>안전요소 3종 충족</div>
    <div class="legend-row"><span class="route"></span>안전 추천 보행경로</div>
    <div class="legend-row"><span class="boundary"></span>창원시 행정경계</div>
  </div>
  <div id="map-error" class="error">네이버 지도를 불러오지 못했습니다.<br>API 서비스와 허용 Web 서비스 URL을 확인해 주세요.</div>
</div>
<script>
  (function(){
  const DATA=__PAYLOAD__;
  const districtColors={"의창구":"#2563EB","성산구":"#F59E0B","마산합포구":"#DC2626","마산회원구":"#16A34A","진해구":"#7C3AED"};
  const groups={};
  const facilityState={};
  let map,infoWindow;
  const esc=(value)=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function addControl(id,label,checked,onChange){const row=document.createElement("label");row.className="layer";const input=document.createElement("input");input.type="checkbox";input.checked=checked;input.addEventListener("change",()=>onChange(input.checked));row.append(input,document.createTextNode(label));document.getElementById("layer-items").appendChild(row);}
  function setObjects(objects,visible){(objects||[]).forEach(o=>o.setMap(visible?map:null));}
  function makeDataLayer(geojson,style){if(!geojson)return null;const layer=new naver.maps.Data({map});layer.addGeoJson(geojson);layer.setStyle(style);return layer;}
  function addGround(image,bounds,opacity){if(!image||!bounds)return null;const b=new naver.maps.LatLngBounds(new naver.maps.LatLng(bounds[0][0],bounds[0][1]),new naver.maps.LatLng(bounds[1][0],bounds[1][1]));const overlay=new naver.maps.GroundOverlay(image,b,{opacity,clickable:false});overlay.setMap(map);return overlay;}
  function openInfo(marker,html){infoWindow.setContent('<div class="info">'+html+'</div>');infoWindow.open(map,marker);}
  function supportMarker(site){const content='<div class="safe-triangle"><svg width="29" height="27" viewBox="0 0 30 28"><polygon points="15,2 28,26 2,26" fill="none" stroke="#fff" stroke-width="6" stroke-linejoin="round"/><polygon points="15,2 28,26 2,26" fill="rgba(22,163,74,.08)" stroke="#16A34A" stroke-width="3" stroke-linejoin="round"/></svg></div>';const marker=new naver.maps.Marker({position:new naver.maps.LatLng(site.lat,site.lng),map,title:"안전요소 3종 충족",icon:{content,size:new naver.maps.Size(30,28),anchor:new naver.maps.Point(15,27)},zIndex:120});naver.maps.Event.addListener(marker,"click",()=>openInfo(marker,'<b style="color:#15803d">안전요소 3종 충족 △</b><br>CCTV 최근접 '+Math.round(site.cctvDistance)+'m<br>보행조명 최근접 '+Math.round(site.lightDistance)+'m<br>공공 Wi-Fi: '+esc(site.place)+'<br>주소: '+esc(site.address)));return marker;}
  function markerContent(kind,count){const symbol=kind==="cctv"?"C":kind==="light"?"L":"W";return '<div class="facility-marker '+kind+'">'+(count>1?count:symbol)+'</div>';}
  function clearFacility(kind){(groups[kind]||[]).forEach(m=>m.setMap(null));groups[kind]=[];}
  function redrawFacility(kind){clearFacility(kind);if(!facilityState[kind])return;const points=DATA.facilities[kind]||[];if(!points.length)return;const zoom=map.getZoom();const bounds=map.getBounds();const cell=zoom>=17?0.00002:0.035/Math.pow(2,Math.max(0,zoom-10));const buckets=new Map();for(const point of points){const pos=new naver.maps.LatLng(point[0],point[1]);if(bounds&&!bounds.hasLatLng(pos))continue;const key=Math.floor(point[0]/cell)+":"+Math.floor(point[1]/cell);let bucket=buckets.get(key);if(!bucket){bucket={lat:0,lng:0,count:0,label:point[2]||""};buckets.set(key,bucket)}bucket.lat+=point[0];bucket.lng+=point[1];bucket.count++}for(const bucket of buckets.values()){const marker=new naver.maps.Marker({position:new naver.maps.LatLng(bucket.lat/bucket.count,bucket.lng/bucket.count),map,title:bucket.count>1?bucket.count+"개 시설":bucket.label,icon:{content:markerContent(kind,bucket.count),size:new naver.maps.Size(30,26),anchor:new naver.maps.Point(15,13)},zIndex:90});if(bucket.label)naver.maps.Event.addListener(marker,"click",()=>openInfo(marker,'<b>'+esc(bucket.label)+'</b><br>'+(bucket.count>1?"주변 시설 "+bucket.count+"개":"원본 시설 위치")));groups[kind].push(marker)}}
  function redrawFacilities(){Object.keys(facilityState).forEach(redrawFacility)}
  function initNaverMap(){
    map=new naver.maps.Map("changwon-naver-map",{center:new naver.maps.LatLng(35.18,128.62),zoom:10,mapTypeControl:true,zoomControl:true,zoomControlOptions:{position:naver.maps.Position.LEFT_CENTER},scaleControl:true});infoWindow=new naver.maps.InfoWindow({borderWidth:0,backgroundColor:"transparent",anchorSize:new naver.maps.Size(12,8)});
    const risk=addGround(DATA.riskImage,DATA.riskBounds,.82);if(risk)addControl("risk","원본 범죄위험 빨간 밀도",true,v=>risk.setMap(v?map:null));
    const grid=addGround(DATA.riskGridImage,DATA.riskBounds,1);if(grid)addControl("grid","고위험 100m 격자",true,v=>grid.setMap(v?map:null));
    const outer=makeDataLayer(DATA.outerBoundary,{strokeColor:"#312E81",strokeWeight:5,strokeOpacity:.95,fillColor:"#312E81",fillOpacity:.02});if(outer)addControl("outer","창원시 외곽경계",true,v=>outer.setMap(v?map:null));
    const districts=makeDataLayer(DATA.districtBoundary,feature=>{const color=districtColors[feature.getProperty("name")]||"#475569";return{strokeColor:color,strokeWeight:4,strokeOpacity:.96,fillColor:color,fillOpacity:.035}});if(districts)addControl("districts","창원시 5개 구 경계",true,v=>districts.setMap(v?map:null));
    groups.support=(DATA.supportSites||[]).map(supportMarker);if(groups.support.length)addControl("support","안전요소 3종 충족 △",true,v=>setObjects(groups.support,v));
    const labels={cctv:"원본 방범용 CCTV",light:"원본 보행조명",wifi:"원본 공공 Wi-Fi"};for(const kind of ["cctv","light","wifi"]){if((DATA.facilities[kind]||[]).length){facilityState[kind]=true;addControl(kind,labels[kind],true,v=>{facilityState[kind]=v;redrawFacility(kind)})}}
    if(DATA.route&&DATA.route.coordinates?.length){const path=DATA.route.coordinates.map(p=>new naver.maps.LatLng(p[0],p[1]));const route=new naver.maps.Polyline({map,path,strokeColor:"#2563EB",strokeWeight:8,strokeOpacity:.95,strokeLineCap:"round",strokeLineJoin:"round",clickable:true,zIndex:150});const start=new naver.maps.Marker({map,position:path[0],title:"출발 · "+DATA.route.startName,icon:{content:'<div class="start-pin">출</div>',size:new naver.maps.Size(34,34),anchor:new naver.maps.Point(17,17)},zIndex:170});const end=new naver.maps.Marker({map,position:path[path.length-1],title:"도착 · "+DATA.route.destinationName,icon:{content:'<div class="end-pin">도</div>',size:new naver.maps.Size(34,34),anchor:new naver.maps.Point(17,17)},zIndex:170});groups.route=[route,start,end];addControl("route","안전 추천 보행경로",true,v=>setObjects(groups.route,v));const routeBounds=new naver.maps.LatLngBounds();path.forEach(p=>routeBounds.extend(p));map.fitBounds(routeBounds,{top:70,right:45,bottom:70,left:45})}
    let redrawTimer;const schedule=()=>{clearTimeout(redrawTimer);redrawTimer=setTimeout(redrawFacilities,180)};naver.maps.Event.addListener(map,"idle",schedule);redrawFacilities();
  }
  window.navermap_authFailure=()=>{document.getElementById("map-error").style.display="flex"};window.initChangwonNaverMap=initNaverMap;
  if(window.naver&&window.naver.maps){initNaverMap()}else{const script=document.createElement("script");script.src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=__CLIENT_ID__&callback=initChangwonNaverMap";script.async=true;script.onerror=window.navermap_authFailure;document.head.appendChild(script)}
  })();
</script>
"""
    return template.replace("__PAYLOAD__", payload_json).replace(
        "__CLIENT_ID__", safe_client_id
    )
