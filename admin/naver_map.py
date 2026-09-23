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
    .safe-triangle{width:29px;height:27px;filter:drop-shadow(0 2px 2px rgba(20,83,45,.65))}.facility-marker{display:flex;align-items:center;justify-content:center;min-width:23px;height:23px;padding:0 4px;border-radius:14px;border:2px solid #fff;color:#fff;font-size:10px;font-weight:900;box-shadow:0 1px 5px rgba(0,0,0,.35)}.cctv{background:#dc2626}.light{background:#ca8a04}.wifi{background:#0284c7}.police{background:#1d4ed8}.start-pin,.end-pin{display:flex;align-items:center;justify-content:center;min-width:48px;height:28px;padding:0 9px;border-radius:16px;border:3px solid white;color:white;font-size:12px;font-weight:900;white-space:nowrap;box-shadow:0 2px 7px rgba(0,0,0,.38)}.start-pin{background:#16a34a}.end-pin{background:#dc2626}.route-arrow{display:flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;border:2px solid #fff;background:#2563eb;color:#fff;font-size:15px;font-weight:900;line-height:24px;box-shadow:0 1px 4px rgba(0,0,0,.35);transform-origin:center}.info{padding:10px 12px;max-width:280px;line-height:1.55;font-size:12px}.info b{font-size:13px}.error{position:absolute;inset:0;display:none;z-index:2000;align-items:center;justify-content:center;background:#f8fafc;color:#b91c1c;font-weight:800;text-align:center;padding:30px}.status{position:absolute;z-index:1800;left:50%;top:50%;transform:translate(-50%,-50%);padding:12px 16px;border-radius:10px;background:rgba(255,255,255,.96);box-shadow:0 3px 14px rgba(15,23,42,.2);color:#334155;font-size:13px;font-weight:800}
    @media(max-width:700px){#layers{top:48px;right:8px;width:185px;padding:8px 10px}.layer{font-size:11px;padding:3px 0}.legend{left:8px;bottom:22px;min-width:160px;padding:8px 10px}.naver-badge{left:8px;top:8px}}
  </style>
<div id="changwon-naver-shell">
  <div id="changwon-naver-map"></div>
  <div class="naver-badge">NAVER 지도 · 창원 안전 인프라 분석</div>
  <div id="map-status" class="status">네이버 지도 SDK 연결 중…</div>
  <div id="layers" class="panel"><div class="panel-title">지도 레이어</div><div id="layer-items"></div></div>
  <div class="legend panel">
    <div class="panel-title">안전 분석 표시</div>
    <div class="legend-row">
  <span class="dot"
        style="background:#F97316;border:2px solid #C2410C"></span>
  생활안전지도 위험 신호
</div>

<div class="legend-row">
  <span class="dot"
        style="background:#DC2626;border:2px solid #991B1B;border-radius:2px"></span>
  4등급 고위험 100m 격자
</div>

<div class="legend-row">
  <span class="dot"
        style="background:#7F1D1D;border:2px solid #450A0A;border-radius:2px"></span>
  5등급 최고위험 100m 격자
</div>
    <div class="legend-row">
  <span id="final-top10-swatch"
        class="dot"
        style="background:#fb923c;border:2px solid #c2410c;border-radius:2px"></span>
  <span id="final-top10-legend-label">최종 안전취약지역 TOP 10</span>
</div>
    <div class="legend-row"><span class="triangle">△</span>안전요소 3종 충족</div>
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
  let map,infoWindow,naver,initialized=false;
  const status=document.getElementById("map-status");
  const fail=(message)=>{status.style.display="none";const error=document.getElementById("map-error");error.innerHTML=message;error.style.display="flex"};
  const esc=(value)=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function addControl(id,label,checked,onChange){const row=document.createElement("label");row.className="layer";const input=document.createElement("input");input.type="checkbox";input.checked=checked;input.addEventListener("change",()=>onChange(input.checked));row.append(input,document.createTextNode(label));document.getElementById("layer-items").appendChild(row);}
  function setObjects(objects,visible){(objects||[]).flat(Infinity).forEach(o=>o.setMap(visible?map:null));}
  function makeDataLayer(geojson,style){if(!geojson)return null;const layer=new naver.maps.Data({map});layer.addGeoJson(geojson);layer.setStyle(style);return layer;}
  function addGround(image,bounds,opacity){if(!image||!bounds)return null;const b=new naver.maps.LatLngBounds(new naver.maps.LatLng(bounds[0][0],bounds[0][1]),new naver.maps.LatLng(bounds[1][0],bounds[1][1]));const overlay=new naver.maps.GroundOverlay(image,b,{opacity,clickable:false});overlay.setMap(map);return overlay;}
  function openInfo(marker,html){infoWindow.setContent('<div class="info">'+html+'</div>');infoWindow.open(map,marker);}
  function supportMarker(site){const content='<div class="safe-triangle"><svg width="29" height="27" viewBox="0 0 30 28"><polygon points="15,2 28,26 2,26" fill="none" stroke="#fff" stroke-width="6" stroke-linejoin="round"/><polygon points="15,2 28,26 2,26" fill="rgba(22,163,74,.08)" stroke="#16A34A" stroke-width="3" stroke-linejoin="round"/></svg></div>';const marker=new naver.maps.Marker({position:new naver.maps.LatLng(site.lat,site.lng),map,title:"안전요소 3종 충족",icon:{content,size:new naver.maps.Size(30,28),anchor:new naver.maps.Point(15,27)},zIndex:120});naver.maps.Event.addListener(marker,"click",()=>openInfo(marker,'<b style="color:#15803d">안전요소 3종 충족 △</b><br>CCTV 최근접 '+Math.round(site.cctvDistance)+'m<br>보행조명 최근접 '+Math.round(site.lightDistance)+'m<br>공공 Wi-Fi: '+esc(site.place)+'<br>주소: '+esc(site.address)));return marker;}
  function priorityZone(zone){const position=new naver.maps.LatLng(zone.lat,zone.lng);const bounds=new naver.maps.LatLngBounds(new naver.maps.LatLng(zone.south,zone.west),new naver.maps.LatLng(zone.north,zone.east));const rectangle=new naver.maps.Rectangle({map,bounds,strokeColor:"#7f1d1d",strokeWeight:3,strokeOpacity:1,fillColor:"#ef4444",fillOpacity:.7,clickable:true,zIndex:145});const label=new naver.maps.Marker({map,position,clickable:false,zIndex:146,icon:{content:'<div style="display:flex;align-items:center;justify-content:center;width:28px;height:24px;border-radius:7px;border:2px solid #fff;background:#991b1b;color:#fff;font-size:12px;font-weight:900;box-shadow:0 1px 5px rgba(0,0,0,.4)">T'+zone.rank+'</div>',size:new naver.maps.Size(28,24),anchor:new naver.maps.Point(14,12)}});naver.maps.Event.addListener(rectangle,"click",()=>{const anchor=new naver.maps.Marker({position,map:null});openInfo(anchor,'<b style="color:#991b1b">추가 설치 필요지역 #'+zone.rank+'</b><br>위치: '+esc(zone.district||"행정구 확인 불가")+'<br>범죄 고위험영역: '+zone.riskPct.toFixed(1)+'% ('+zone.riskScore+'/5점)<br>인프라 부족도: '+zone.deficitScore.toFixed(2)+'/5점<br>최종 취약도: '+zone.priorityScore.toFixed(2)+'/5점 ('+zone.priorityGrade+'등급)<br>연속 고취약 격자: '+zone.clusterGridCount+'개<br>안전 인프라: '+zone.infraCount+'/3개 ('+zone.infraScore.toFixed(2)+'/5점)<br>CCTV: '+(zone.cctv?"충족":"미충족")+' · 보안등: '+(zone.light?"충족":"미충족")+' · Wi-Fi: '+(zone.wifi?"충족":"미충족")+'<br>최근접 파출소: '+Math.round(zone.policeDistance)+'m<br>'+esc(zone.targetLabel)+' 영향권: '+esc(zone.targetInfluence)+'<br>부족 시설: '+esc(zone.missing)+'<br>선정 이유: '+esc(zone.reason))});return [rectangle,label];}
 
function finalTop10Layer(){
  const geojson=DATA.finalTop10;
  if(!geojson||!geojson.features?.length)return [];

  const isChild=DATA.finalTop10Target==="어린이";
  const strokeColor=isChild?"#C2410C":"#6D28D9";
  const fillColor=isChild?"#FB923C":"#8B5CF6";
  const badgeColor=isChild?"#C2410C":"#6D28D9";
  const targetLabel=DATA.finalTop10Target||"";

  const legendSwatch=document.getElementById("final-top10-swatch");
const legendLabel=document.getElementById("final-top10-legend-label");

if(legendSwatch){
  legendSwatch.style.background=fillColor;
  legendSwatch.style.borderColor=strokeColor;
}

if(legendLabel){
  legendLabel.textContent=
    (targetLabel?targetLabel+" ":"")+
    "최종 안전취약지역 TOP 10";
}
  
  const layer=new naver.maps.Data({map});
  layer.addGeoJson(geojson);

  layer.setStyle({
    strokeColor:strokeColor,
    strokeWeight:4,
    strokeOpacity:1,
    fillColor:fillColor,
    fillOpacity:.42,
    clickable:true,
    zIndex:145
  });

  naver.maps.Event.addListener(layer,"mouseover",e=>{
    layer.overrideStyle(e.feature,{
      strokeWeight:6,
      fillOpacity:.68
    });
  });

  naver.maps.Event.addListener(layer,"mouseout",e=>{
    layer.revertStyle(e.feature);
  });

  naver.maps.Event.addListener(layer,"click",e=>{
    const f=e.feature;

    const label=f.getProperty("top10_label")||"TOP10";
    const cluster=f.getProperty("cluster_id")||"-";
    const risk=Number(f.getProperty("risk_pct_mean")||0);
    const infra=Number(f.getProperty("infra_need_mean")||0);
    const vulnerability=Number(f.getProperty("vulnerability_mean")||0);
    const gridN=Number(f.getProperty("grid_n")||0);

    const cctvNeeded=Boolean(f.getProperty("cctv_needed"));
    const lightNeeded=Boolean(f.getProperty("light_needed"));
    const wifiNeeded=Boolean(f.getProperty("wifi_needed"));

    const primary=f.getProperty("primary_facility")||"-";
    const order=f.getProperty("facility_priority_order")||"-";
    const recommendType=f.getProperty("recommendation_type")||"-";

    const policeDistance=f.getProperty("police_distance_mean_km");
    const policeReference=f.getProperty("police_access_reference");

    let policeHtml="";
    if(
      DATA.finalTop10Target==="노인" &&
      policeDistance!==null &&
      policeDistance!==undefined
    ){
      policeHtml=
        '<br><span style="color:#475569"><b>경찰 접근성 참고</b>: '+
        Number(policeDistance).toFixed(3)+' km'+
        (policeReference?' · '+esc(policeReference):'')+
        '</span>'+
        '<br><span style="color:#64748b;font-size:11px">'+
        '※ 최종 취약점수와 시설 우선순위에는 미반영'+
        '</span>';
    }

    const statusBadge=(needed,labelText)=>
      '<span style="display:inline-block;margin:2px 4px 2px 0;padding:3px 7px;border-radius:7px;'+
      (needed
        ?'background:#fee2e2;color:#991b1b'
        :'background:#dcfce7;color:#166534')+
      ';font-weight:800">'+
      (needed?'＋ ':'✓ ')+esc(labelText)+(needed?' 보완 필요':' 충족')+
      '</span>';

    infoWindow.setContent(
      '<div class="info" style="min-width:300px">'+
      '<div style="display:flex;justify-content:space-between;gap:10px;align-items:center">'+
      '<b style="color:'+strokeColor+';font-size:15px">'+esc(label)+'</b>'+
      '<span style="color:#64748b;font-weight:800">'+esc(cluster)+'</span>'+
      '</div>'+
      '<hr style="border:0;border-top:1px solid #e2e8f0;margin:8px 0">'+
      '<b>범죄 고위험 적색영역 비율</b>: '+risk.toFixed(2)+'%<br>'+
      '<b>CRITIC 인프라 부족점수</b>: '+infra.toFixed(4)+'<br>'+
      '<b>최종 취약점수</b>: '+vulnerability.toFixed(4)+'<br>'+
      '<b>포함 격자</b>: '+gridN+'개<br>'+
      '<div style="margin:8px 0">'+
      statusBadge(cctvNeeded,"CCTV")+
      statusBadge(lightNeeded,"보안등")+
      statusBadge(wifiNeeded,"공공 Wi-Fi")+
      '</div>'+
      '<div style="padding:9px 10px;border-radius:9px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412">'+
      '<b>1순위 보완시설: '+esc(primary)+'</b><br>'+
      '보완 순서: '+esc(order)+'<br>'+
      esc(recommendType)+
      '</div>'+
      policeHtml+
      '</div>'
    );

    const lat=f.getProperty("latitude");
    const lng=f.getProperty("longitude");
    const position=e.coord||(
      lat!=null&&lng!=null
        ?new naver.maps.LatLng(Number(lat),Number(lng))
        :map.getCenter()
    );

    infoWindow.setPosition(position);
    infoWindow.open(map);
  });

  const labels=(geojson.features||[]).map(feature=>{
    const p=feature.properties||{};

    if(
      p.latitude==null ||
      p.longitude==null ||
      p.cluster_rank==null
    )return null;

    const primary=String(p.primary_facility||"");

    const symbol=
      primary==="보안등"?"💡":
      primary==="CCTV"?"📹":
      primary.includes("Wi-Fi")||primary.includes("와이파이")
        ?"Wi-Fi":"";

    return new naver.maps.Marker({
      map,
      position:new naver.maps.LatLng(
        Number(p.latitude),
        Number(p.longitude)
      ),
      title:
        (p.top10_label||("TOP "+p.cluster_rank))+
        " · 1순위 "+primary,
      clickable:false,
      zIndex:146,
      icon:{
        content:
          '<div style="'+
          'display:flex;align-items:center;justify-content:center;'+
          'min-width:54px;height:28px;padding:0 7px;'+
          'border-radius:8px;border:2px solid white;'+
          'background:'+badgeColor+';color:white;'+
          'font-size:11px;font-weight:900;white-space:nowrap;'+
          'box-shadow:0 2px 7px rgba(0,0,0,.38)">'+
          'TOP '+Number(p.cluster_rank)+(symbol?' · '+symbol:'')+
          '</div>',
        size:new naver.maps.Size(66,28),
        anchor:new naver.maps.Point(33,14)
      }
    });
  }).filter(Boolean);

  return [layer,...labels];
}  
  function markerContent(kind,count){const symbols={cctv:"C",light:"L",wifi:"W",police:"P"};return '<div class="facility-marker '+kind+'">'+(count>1?count:symbols[kind])+'</div>';}
  function clearFacility(kind){(groups[kind]||[]).forEach(m=>m.setMap(null));groups[kind]=[];}
  function redrawFacility(kind){clearFacility(kind);if(!facilityState[kind])return;const points=DATA.facilities[kind]||[];if(!points.length)return;const zoom=map.getZoom();const bounds=map.getBounds();const cell=zoom>=17?0.00002:0.035/Math.pow(2,Math.max(0,zoom-10));const buckets=new Map();for(const point of points){const pos=new naver.maps.LatLng(point[0],point[1]);if(bounds&&!bounds.hasLatLng(pos))continue;const key=Math.floor(point[0]/cell)+":"+Math.floor(point[1]/cell);let bucket=buckets.get(key);if(!bucket){bucket={lat:0,lng:0,count:0,label:point[2]||"",address:point[3]||""};buckets.set(key,bucket)}bucket.lat+=point[0];bucket.lng+=point[1];bucket.count++}for(const bucket of buckets.values()){const marker=new naver.maps.Marker({position:new naver.maps.LatLng(bucket.lat/bucket.count,bucket.lng/bucket.count),map,title:bucket.count>1?bucket.count+"개 시설":bucket.label,icon:{content:markerContent(kind,bucket.count),size:new naver.maps.Size(30,26),anchor:new naver.maps.Point(15,13)},zIndex:90});if(bucket.label)naver.maps.Event.addListener(marker,"click",()=>openInfo(marker,kind==="police"&&bucket.count===1?'<b>'+esc(bucket.label)+'</b><br>주소: '+esc(bucket.address):'<b>'+esc(bucket.label)+'</b><br>'+(bucket.count>1?"주변 시설 "+bucket.count+"개":"원본 시설 위치")));groups[kind].push(marker)}}
  function redrawFacilities(){Object.keys(facilityState).forEach(redrawFacility)}
  function initNaverMap(){
    try{
    naver=window.naver;
    status.textContent="네이버 지도와 안전 데이터를 불러오는 중…";
    const focus=DATA.focus||{lat:35.18,lng:128.62,zoom:10,name:"창원시"};map=new naver.maps.Map("changwon-naver-map",{center:new naver.maps.LatLng(focus.lat,focus.lng),zoom:focus.zoom||10,mapTypeControl:true,zoomControl:true,zoomControlOptions:{position:naver.maps.Position.LEFT_CENTER},scaleControl:true});infoWindow=new naver.maps.InfoWindow({borderWidth:0,backgroundColor:"transparent",anchorSize:new naver.maps.Size(12,8)});if((focus.zoom||10)>10)new naver.maps.Marker({map,position:new naver.maps.LatLng(focus.lat,focus.lng),title:focus.name||"검색 위치",zIndex:180});
    const risk=addGround(
  DATA.riskImage,
  DATA.riskBounds,
  .62
);

if(risk){
  risk.setMap(null);

  addControl(
    "risk",
    "생활안전지도 위험 신호 (참고)",
    false,
    v=>risk.setMap(v?map:null)
  );
}

const grid=addGround(
  DATA.riskGridImage,
  DATA.riskBounds,
  .90
);

if(grid){
  addControl(
    "grid",
    "고위험 100m 격자 (4~5등급)",
    true,
    v=>grid.setMap(v?map:null)
  );
}

const outer=makeDataLayer(
  DATA.outerBoundary,
  {
    strokeColor:"#312E81",
    strokeWeight:6,
    strokeOpacity:1,
    fillColor:"#312E81",
    fillOpacity:.01,
    zIndex:134
  }
);

const districts=makeDataLayer(
  DATA.districtBoundary,
  feature=>{
    const color=
      districtColors[feature.getProperty("name")]||
      "#475569";

    return{
      strokeColor:color,
      strokeWeight:4,
      strokeOpacity:.95,
      fillColor:color,
      fillOpacity:.018,
      zIndex:135
    };
  }
);

if(outer){
  outer.setMap(null);
  outer.setMap(map);
}

if(districts){
  districts.setMap(null);
  districts.setMap(map);
}

groups.boundaryLayers=[
  outer,
  districts
].filter(Boolean);

if(groups.boundaryLayers.length){
  addControl(
    "boundaries",
    "창원시 행정경계",
    true,
    v=>setObjects(groups.boundaryLayers,v)
  );
}
    groups.priority=(DATA.priorityZones||[]).map(priorityZone);if(groups.priority.length)addControl("priority","추가 설치 필요지역 TOP 10",true,v=>setObjects(groups.priority,v));
    groups.finalTop10=finalTop10Layer();

if(groups.finalTop10.length){
  const finalLabel=
    (DATA.finalTop10Target?DATA.finalTop10Target+" ":"")+
    "최종 안전취약지역 TOP 10";

  addControl(
    "finalTop10",
    finalLabel,
    true,
    v=>setObjects(groups.finalTop10,v)
  );
}
    const labels={cctv:"원본 방범용 CCTV",light:"원본 보행조명",wifi:"원본 공공 Wi-Fi",police:"원본 지구대·파출소"};for(const kind of ["cctv","light","wifi","police"]){if((DATA.facilities[kind]||[]).length){facilityState[kind]=false;addControl(kind,labels[kind],false,v=>{facilityState[kind]=v;redrawFacility(kind)})}}
    if(DATA.route&&DATA.route.coordinates?.length){
      const path=DATA.route.coordinates.map(p=>new naver.maps.LatLng(p[0],p[1]));
      const route=new naver.maps.Polyline({map,path,strokeColor:"#2563EB",strokeWeight:8,strokeOpacity:.95,strokeLineCap:"round",strokeLineJoin:"round",clickable:true,zIndex:150});
      const start=new naver.maps.Marker({map,position:path[0],title:"출발 · "+DATA.route.startName,icon:{content:'<div class="start-pin">출발</div>',size:new naver.maps.Size(66,36),anchor:new naver.maps.Point(33,18)},zIndex:170});
      const end=new naver.maps.Marker({map,position:path[path.length-1],title:"도착 · "+DATA.route.destinationName,icon:{content:'<div class="end-pin">도착</div>',size:new naver.maps.Size(66,36),anchor:new naver.maps.Point(33,18)},zIndex:170});
      const arrows=[];
      const arrowCount=Math.min(12,Math.max(4,Math.floor(path.length/18)));
      for(let i=1;i<=arrowCount;i++){
        const index=Math.min(path.length-2,Math.max(1,Math.floor(i*(path.length-1)/(arrowCount+1))));
        const before=path[Math.max(0,index-1)],after=path[Math.min(path.length-1,index+1)];
        const angle=Math.atan2(-(after.lat()-before.lat()),after.lng()-before.lng())*180/Math.PI;
        arrows.push(new naver.maps.Marker({map,position:path[index],title:"진행 방향",icon:{content:'<div class="route-arrow" style="transform:rotate('+angle+'deg)">➤</div>',size:new naver.maps.Size(24,24),anchor:new naver.maps.Point(12,12)},clickable:false,zIndex:165}));
      }
      groups.route=[route,...arrows,start,end];
      addControl("route","안전 추천 보행경로",true,v=>setObjects(groups.route,v));
      const routeBounds=new naver.maps.LatLngBounds();path.forEach(p=>routeBounds.extend(p));map.fitBounds(routeBounds,{top:70,right:45,bottom:70,left:45})
    }
    let redrawTimer;const schedule=()=>{clearTimeout(redrawTimer);redrawTimer=setTimeout(redrawFacilities,180)};naver.maps.Event.addListener(map,"idle",schedule);redrawFacilities();initialized=true;status.style.display="none";
    }catch(error){console.error(error);fail("네이버 지도 초기화 중 오류가 발생했습니다.<br><small>"+esc(error?.message||error)+"</small>")}
  }
  window.navermap_authFailure=()=>fail("네이버 지도 인증에 실패했습니다.<br>Web Dynamic Map 사용 설정과 허용 URL을 확인해 주세요.");
  if(window.naver&&window.naver.maps){initNaverMap()}else{const script=document.createElement("script");script.src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=__CLIENT_ID__";script.async=true;script.onload=()=>{if(window.naver&&window.naver.maps)initNaverMap();else fail("네이버 지도 SDK 응답이 올바르지 않습니다.<br>Dynamic Map 사용 설정을 확인해 주세요.")};script.onerror=()=>fail("네이버 지도 SDK를 불러오지 못했습니다.<br>잠시 후 새로고침해 주세요.");document.head.appendChild(script);setTimeout(()=>{if(!initialized)fail("네이버 지도 연결 시간이 초과되었습니다.<br>API의 Web 서비스 URL 등록 상태를 확인해 주세요.")},10000)}
  })();
</script>
"""
    return template.replace("__PAYLOAD__", payload_json).replace(
        "__CLIENT_ID__", safe_client_id
    )

def build_naver_location_map_html(
    client_id: str,
    feature: dict | None,
    latitude: float,
    longitude: float,
    target_label: str,
    top10_label: str,
    cctv_points: list[dict] | None = None,
) -> str:
    """TOP10 위치 모달용 간단한 NAVER 지도를 생성합니다."""
    feature_json = json.dumps(
        feature,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    cctv_json = json.dumps(
        cctv_points or [],
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")

    safe_client_id = quote(client_id, safe="")

    line_color = (
        "#C2410C"
        if target_label == "어린이"
        else "#6D28D9"
    )
    fill_color = (
        "#FB923C"
        if target_label == "어린이"
        else "#8B5CF6"
    )

    template = r"""
<style>
html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 430px;
    overflow: hidden;
}

#top10-location-shell {
    position: relative;
    width: 100%;
    height: 430px;
    background: #eef2f7;
    font-family: Pretendard, "Noto Sans KR", sans-serif;
}

#top10-location-map {
    width: 100%;
    height: 100%;
}

#top10-location-status {
    position: absolute;
    z-index: 1000;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    padding: 10px 14px;
    border-radius: 9px;
    background: rgba(255,255,255,.96);
    box-shadow: 0 3px 14px rgba(15,23,42,.18);
    color: #334155;
    font-size: 13px;
    font-weight: 800;
}

#top10-location-error {
    position: absolute;
    inset: 0;
    z-index: 1100;
    display: none;
    align-items: center;
    justify-content: center;
    background: #f8fafc;
    color: #b91c1c;
    font-size: 13px;
    font-weight: 800;
    text-align: center;
}
</style>

<div id="top10-location-shell">
    <div id="top10-location-map"></div>

    <div id="top10-location-status">
        NAVER 지도를 불러오는 중…
    </div>

    <div id="top10-location-error">
        NAVER 지도를 불러오지 못했습니다.
    </div>
</div>

<script>
(function () {
    const FEATURE = __FEATURE__;
    const LATITUDE = __LATITUDE__;
    const LONGITUDE = __LONGITUDE__;
    const LINE_COLOR = "__LINE_COLOR__";
    const FILL_COLOR = "__FILL_COLOR__";
    const TOP10_LABEL = "__TOP10_LABEL__";
    const CCTV_POINTS = __CCTV_POINTS__;

    let initialized = false;

    const status = document.getElementById(
        "top10-location-status"
    );

    const errorBox = document.getElementById(
        "top10-location-error"
    );

    function fail(message) {
        status.style.display = "none";
        errorBox.innerHTML = message;
        errorBox.style.display = "flex";
    }

    function initializeMap() {
        try {
            const naver = window.naver;

            const center = new naver.maps.LatLng(
                LATITUDE,
                LONGITUDE
            );

            const map = new naver.maps.Map(
                "top10-location-map",
                {
                    center: center,
                    zoom: 17,
                    zoomControl: true,
                    zoomControlOptions: {
                        position:
                            naver.maps.Position.LEFT_CENTER
                    },
                    scaleControl: true,
                    mapTypeControl: false
                }
            );

            let coordinateCount = 0;

            if (
                FEATURE &&
                FEATURE.geometry &&
                FEATURE.geometry.coordinates
            ) {
                const bounds =
                    new naver.maps.LatLngBounds();

                function makePath(ring) {
                    return ring.map(function (coordinate) {
                        const lng = Number(coordinate[0]);
                        const lat = Number(coordinate[1]);

                        const point =
                            new naver.maps.LatLng(
                                lat,
                                lng
                            );

                        bounds.extend(point);
                        coordinateCount += 1;

                        return point;
                    });
                }

                function drawPolygon(rings) {
                    const paths = rings.map(
                        function (ring) {
                            return makePath(ring);
                        }
                    );

                    new naver.maps.Polygon({
                        map: map,
                        paths: paths,
                        strokeColor: LINE_COLOR,
                        strokeWeight: 4,
                        strokeOpacity: 1,
                        fillColor: FILL_COLOR,
                        fillOpacity: 0.42,
                        clickable: false,
                        zIndex: 150
                    });
                }

                if (
                    FEATURE.geometry.type === "Polygon"
                ) {
                    drawPolygon(
                        FEATURE.geometry.coordinates
                    );
                }

                if (
                    FEATURE.geometry.type === "MultiPolygon"
                ) {
                    FEATURE.geometry.coordinates.forEach(
                        function (polygon) {
                            drawPolygon(polygon);
                        }
                    );
                }

                if (coordinateCount > 0) {
                    map.fitBounds(
                        bounds,
                        {
                            top: 55,
                            right: 55,
                            bottom: 55,
                            left: 55
                        }
                    );
                }
            }

            CCTV_POINTS.forEach(function (point) {
                const position = new naver.maps.LatLng(
                    Number(point.lat),
                    Number(point.lng)
                );

                const inAnalysisRange =
                    Boolean(point.in_analysis_range);

                const markerBackground =
                    inAnalysisRange
                        ? "#DC2626"
                        : "#FCA5A5";

                const markerBorder =
                    inAnalysisRange
                        ? "#991B1B"
                        : "#DC2626";

                const markerText =
                    inAnalysisRange
                        ? "#FFFFFF"
                        : "#7F1D1D";

                const marker = new naver.maps.Marker({
                    map: map,
                    position: position,
                    title: inAnalysisRange
                        ? "CCTV · 분석 기준 100m 이내"
                        : "CCTV · 주변 300m 이내",
                    zIndex: inAnalysisRange ? 175 : 165,
                    icon: {
                        content:
                            '<div style="' +
                            'display:flex;' +
                            'align-items:center;' +
                            'justify-content:center;' +
                            'width:24px;' +
                            'height:24px;' +
                            'border-radius:50%;' +
                            'border:2px solid ' +
                            markerBorder + ';' +
                            'background:' +
                            markerBackground + ';' +
                            'color:' +
                            markerText + ';' +
                            'font-size:10px;' +
                            'font-weight:900;' +
                            'box-shadow:0 1px 5px rgba(0,0,0,.28)">' +
                            'C' +
                            '</div>',
                        size: new naver.maps.Size(24, 24),
                        anchor: new naver.maps.Point(12, 12)
                    }
                });

                const rangeLabel =
                    inAnalysisRange
                        ? "분석 기준 100m 이내"
                        : "주변 참고 100~300m";

                const info = new naver.maps.InfoWindow({
                    content:
                        '<div style="' +
                        'padding:9px 11px;' +
                        'font-size:12px;' +
                        'line-height:1.55">' +
                        '<b>CCTV</b><br>' +
                        rangeLabel + '<br>' +
                        '중심점 거리 · ' +
                        Number(point.distance).toFixed(1) +
                        'm' +
                        (
                            point.address
                                ? '<br>' + String(point.address)
                                : ''
                        ) +
                        '</div>'
                });

                naver.maps.Event.addListener(
                    marker,
                    "click",
                    function () {
                        info.open(map, marker);
                    }
                );
            });

            if (CCTV_POINTS.length > 0) {
                map.setCenter(center);
                map.setZoom(16);
            }
            
            new naver.maps.Marker({
                map: map,
                position: center,
                title: TOP10_LABEL + " 중심 위치",
                zIndex: 180
            });

            initialized = true;
            status.style.display = "none";

        } catch (error) {
            console.error(error);

            fail(
                "NAVER 지도 초기화 중 오류가 발생했습니다."
            );
        }
    }

    window.navermap_authFailure = function () {
        fail(
            "NAVER 지도 인증에 실패했습니다.<br>" +
            "Web Dynamic Map 설정을 확인해 주세요."
        );
    };

    if (
        window.naver &&
        window.naver.maps
    ) {
        initializeMap();

    } else {
        const script =
            document.createElement("script");

        script.src =
            "https://oapi.map.naver.com/openapi/v3/maps.js" +
            "?ncpKeyId=__CLIENT_ID__";

        script.async = true;

        script.onload = function () {
            if (
                window.naver &&
                window.naver.maps
            ) {
                initializeMap();
            } else {
                fail(
                    "NAVER 지도 SDK를 불러오지 못했습니다."
                );
            }
        };

        script.onerror = function () {
            fail(
                "NAVER 지도 SDK 연결에 실패했습니다."
            );
        };

        document.head.appendChild(script);

        setTimeout(function () {
            if (!initialized) {
                fail(
                    "NAVER 지도 연결 시간이 초과되었습니다."
                );
            }
        }, 10000);
    }
})();
</script>
"""

    return (
        template
        .replace("__FEATURE__", feature_json)
        .replace("__LATITUDE__", str(float(latitude)))
        .replace("__LONGITUDE__", str(float(longitude)))
        .replace("__LINE_COLOR__", line_color)
        .replace("__FILL_COLOR__", fill_color)
        .replace(
            "__TOP10_LABEL__",
            str(top10_label).replace('"', '\\"'),
        )
        .replace("__CCTV_POINTS__", cctv_json)
        .replace("__CLIENT_ID__", safe_client_id)
    )
