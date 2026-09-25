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
  <span style="display:inline-block;width:22px;height:10px;border-radius:3px;
        background:linear-gradient(90deg,#FCD34D,#F59E0B,#B45309)"></span>
  원본 범죄위험 지도 (진할수록 위험)
</div>

<div class="legend-row" style="margin-top:8px;font-weight:900">
  범죄 고위험 면적 비율 (100m 격자)
  <span style="font-weight:600;color:#64748b;font-size:10.5px">· 확대 시 표시</span>
</div>

<div class="legend-row" style="margin:2px 0 0 0;color:#64748b;font-size:10px;font-weight:700;white-space:nowrap">
  <span style="display:inline-block;width:34px;text-align:center">격자만</span>
  <span style="display:inline-block;width:52px;text-align:center">원본과 함께</span>
</div>

<div class="legend-row">
  <span style="display:inline-block;width:34px;text-align:center"><span style="display:inline-block;width:13px;height:13px;border-radius:2px;box-sizing:border-box;background:#FCA5A5;border:2px solid #F87171"></span></span>
  <span style="display:inline-block;width:52px;text-align:center"><span style="display:inline-block;width:13px;height:13px;border-radius:2px;box-sizing:border-box;border:1.5px dashed #F87171"></span></span>
  10% 미만
</div>

<div class="legend-row">
  <span style="display:inline-block;width:34px;text-align:center"><span style="display:inline-block;width:13px;height:13px;border-radius:2px;box-sizing:border-box;background:#EF4444;border:2px solid #B91C1C"></span></span>
  <span style="display:inline-block;width:52px;text-align:center"><span style="display:inline-block;width:13px;height:13px;border-radius:2px;box-sizing:border-box;border:2.5px solid #DC2626"></span></span>
  10 ~ 25%
</div>

<div class="legend-row">
  <span style="display:inline-block;width:34px;text-align:center"><span style="display:inline-block;width:13px;height:13px;border-radius:2px;box-sizing:border-box;background:#991B1B;border:2px solid #450A0A"></span></span>
  <span style="display:inline-block;width:52px;text-align:center"><span style="display:inline-block;width:13px;height:13px;border-radius:2px;box-sizing:border-box;background:rgba(127,29,29,.12);border:3px solid #7F1D1D"></span></span>
  25% 이상
</div>

<div style="margin:3px 0 6px 0;color:#64748b;font-size:10.5px;font-weight:600;line-height:1.45;width:200px;word-break:keep-all">
  ※ 100m 칸 안에서 경찰청 최고위험(적색) 구역이 차지하는 면적 (25% = 칸의 1/4)
</div>
    <div class="legend-row">
  <span id="final-top10-swatch"
        class="dot"
        style="background:#fb923c;border:2px solid #c2410c;border-radius:2px"></span>
  <span id="final-top10-legend-label">최종 안전취약지역 TOP 10</span>
</div>
    <div class="legend-row"><span class="triangle">△</span>안전요소 3종 충족 격자 <span style="font-weight:600;color:#64748b;font-size:10.5px">· 체크 시 표시</span></div>
    <div class="legend-row"><span class="boundary" style="border-top:3px solid #475569"></span>창원시 행정경계 (5개 구)</div>
  </div>
  <div id="map-error" class="error">네이버 지도를 불러오지 못했습니다.<br>API 서비스와 허용 Web 서비스 URL을 확인해 주세요.</div>
</div>
<script>
  (function(){
  const DATA=__PAYLOAD__;
  const districtColors={"의창구":"#475569","성산구":"#475569","마산합포구":"#475569","마산회원구":"#475569","진해구":"#475569"};
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
  const top10Geojson=Object.assign({},geojson);
  delete top10Geojson.crs;
  layer.addGeoJson(top10Geojson);

  layer.setStyle({
    strokeColor:strokeColor,
    strokeWeight:4,
    strokeOpacity:1,
    fillColor:fillColor,
    fillOpacity:.42,
    clickable:true,
    zIndex:145
  });

  const reattachTop10=()=>{
    layer.setMap(null);
    layer.setMap(map);
  };
  naver.maps.Event.once(map,"idle",reattachTop10);
  setTimeout(reattachTop10,800);

  const hoverInfo=new naver.maps.InfoWindow({
    borderWidth:1,
    borderColor:strokeColor,
    backgroundColor:"#ffffff",
    anchorSize:new naver.maps.Size(8,8),
    disableAutoPan:true
  });

  const facilityIcon=name=>
    name==="보안등"?"💡":
    name==="CCTV"?"📹":
    "📶";

  const hoverHtml=p=>
    '<div style="padding:8px 11px;font-size:12px;line-height:1.6;min-width:170px">'+
    '<b style="color:'+strokeColor+';font-size:13px">'+
    esc(p.top10_label||"TOP10")+'</b><br>'+
    (p.address?'📍 '+esc(p.address)+'<br>':'')+
    '최종 취약점수 <b>'+Number(p.vulnerability_mean||0).toFixed(3)+'</b><br>'+
    facilityIcon(p.primary_facility)+' <b>'+esc(p.primary_facility||"-")+
    ' 우선 설치 권장</b><br>'+
    '<span style="color:#64748b;font-size:11px">('+
    esc(p.facility_priority_order||"-")+')</span>'+
    '</div>';

  const showHover=(p,position)=>{
    hoverInfo.setContent(hoverHtml(p));
    hoverInfo.open(map,position);
  };

  const featureHoverProps=f=>({
    top10_label:f.getProperty("top10_label"),
    address:f.getProperty("address"),
    vulnerability_mean:f.getProperty("vulnerability_mean"),
    primary_facility:f.getProperty("primary_facility"),
    facility_priority_order:f.getProperty("facility_priority_order")
  });

  const top10LabelMarkers={};
  let top10InfoOpenedAt=0;
  naver.maps.Event.addListener(map,"click",()=>{
    hoverInfo.close();
    if(Date.now()-top10InfoOpenedAt>400){
      infoWindow.close();
    }
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
    hoverInfo.close();

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

    const address=f.getProperty("address")||"";
    const centerLat=Number(f.getProperty("latitude")||0);
    const centerLng=Number(f.getProperty("longitude")||0);

    infoWindow.setContent(
      '<div class="info" style="background:#ffffff;border:1px solid #cbd5e1;'+
      'border-radius:10px;box-shadow:0 3px 12px rgba(15,23,42,.18);'+
      'padding:8px 11px;white-space:nowrap">'+
      '<b style="color:'+strokeColor+';font-size:14px">'+esc(label)+'</b><br>'+
      '📍 '+(
        address
          ?esc(address)
          :centerLat.toFixed(5)+', '+centerLng.toFixed(5)
      )+'<br>'+
      '<span style="color:#9a3412;font-weight:800">'+
      '1순위 보완: '+esc(primary)+
      '</span>'+
      '</div>'
    );

    top10InfoOpenedAt=Date.now();
    const anchorMarker=top10LabelMarkers[String(f.getProperty("cluster_id"))];

    if(anchorMarker){
      infoWindow.open(map,anchorMarker);
    }else{
      infoWindow.setPosition(
        e.coord||new naver.maps.LatLng(centerLat,centerLng)
      );
      infoWindow.open(map);
    }
  });

  const top10LabelIcon=(rank,compact)=>{
    if(compact){
      return{
        content:
          '<div style="display:flex;align-items:center;justify-content:center;'+
          'width:20px;height:20px;border-radius:50%;border:1.5px solid white;'+
          'background:'+badgeColor+';color:white;font-size:11px;font-weight:900;'+
          'box-shadow:0 1px 4px rgba(0,0,0,.35)">'+
          Number(rank)+
          '</div>',
        size:new naver.maps.Size(20,20),
        anchor:new naver.maps.Point(10,10)
      };
    }
    return{
      content:
        '<div style="width:52px;text-align:center">'+
        '<div style="position:relative;display:inline-block;'+
        'padding:3px 7px;border-radius:6px;border:1.5px solid white;'+
        'background:'+badgeColor+';color:white;'+
        'font-size:10px;font-weight:900;line-height:12px;white-space:nowrap;'+
        'box-shadow:0 1px 4px rgba(0,0,0,.35)">'+
        'TOP '+Number(rank)+
        '<span style="position:absolute;left:50%;bottom:-6px;'+
        'transform:translateX(-50%);width:0;height:0;'+
        'border-left:5px solid transparent;border-right:5px solid transparent;'+
        'border-top:6px solid '+badgeColor+'"></span>'+
        '</div></div>',
      size:new naver.maps.Size(52,27),
      anchor:new naver.maps.Point(26,27)
    };
  };
  
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

    let topLatitude=-Infinity;
    const findTop=coordinates=>{
      if(typeof coordinates[0]==="number"){
        topLatitude=Math.max(topLatitude,Number(coordinates[1]));
      }else{
        coordinates.forEach(findTop);
      }
    };
    if(feature.geometry&&feature.geometry.coordinates){
      findTop(feature.geometry.coordinates);
    }
    const labelLatitude=
      Number.isFinite(topLatitude)?topLatitude:Number(p.latitude);

    const labelMarker=new naver.maps.Marker({
      map,
      position:new naver.maps.LatLng(
        labelLatitude,
        Number(p.longitude)
      ),
      title:
        (p.top10_label||("TOP "+p.cluster_rank))+
        " · 1순위 "+primary,
      clickable:true,
      zIndex:146,
      icon:top10LabelIcon(p.cluster_rank,map.getZoom()<=13)
    });
    labelMarker.top10Rank=Number(p.cluster_rank);
    top10LabelMarkers[String(p.cluster_id)]=labelMarker;

    naver.maps.Event.addListener(labelMarker,"click",()=>{
      infoWindow.close();
      const target=new naver.maps.LatLng(
        Number(p.latitude),
        Number(p.longitude)
      );
      if(typeof map.morph==="function"){
        map.morph(target,17);
      }else{
        map.setCenter(target);
        map.setZoom(17);
      }
      const clickedFeature=layer.getAllFeatures().find(item=>
        String(item.getProperty("cluster_id"))===String(p.cluster_id)
      );
      if(clickedFeature){
        naver.maps.Event.trigger(layer,"click",{feature:clickedFeature});
      }
    });

    return labelMarker;
  }).filter(Boolean);

  const naverShell=document.getElementById("changwon-naver-shell");
  if(naverShell&&labels.length){
    const jumpPanel=document.createElement("div");
    jumpPanel.className="panel";
    jumpPanel.style.cssText="right:12px;bottom:40px;width:176px;padding:9px 10px";
    jumpPanel.innerHTML=
      '<div class="panel-title" style="font-size:12px;margin-bottom:6px">'+
      esc(targetLabel)+' TOP 바로가기</div>';
    const jumpGrid=document.createElement("div");
    jumpGrid.style.cssText="display:grid;grid-template-columns:repeat(5,1fr);gap:5px";
    labels
      .slice()
      .sort((a,b)=>a.top10Rank-b.top10Rank)
      .forEach(marker=>{
        const button=document.createElement("button");
        button.type="button";
        button.textContent=marker.top10Rank;
        button.title="TOP "+marker.top10Rank+" 위치로 이동";
        button.style.cssText=
          "height:26px;border:0;border-radius:7px;cursor:pointer;"+
          "background:"+badgeColor+";color:#fff;font-size:12px;font-weight:900";
        button.addEventListener("click",()=>{
          naver.maps.Event.trigger(marker,"click");
        });
        jumpGrid.appendChild(button);
      });
    jumpPanel.appendChild(jumpGrid);
    naverShell.appendChild(jumpPanel);
  }
  let compactLabels=map.getZoom()<=13;
  naver.maps.Event.addListener(map,"zoom_changed",()=>{
    const compact=map.getZoom()<=13;
    if(compact===compactLabels)return;
    compactLabels=compact;
    labels.forEach(marker=>{
      marker.setIcon(top10LabelIcon(marker.top10Rank,compact));
    });
  });

  return [layer,...labels];
}  
  function markerContent(kind,count){const symbols={cctv:"C",light:"L",wifi:"W",police:"P"};return '<div class="facility-marker '+kind+'">'+(count>1?count:symbols[kind])+'</div>';}
  function clearFacility(kind){(groups[kind]||[]).forEach(m=>m.setMap(null));groups[kind]=[];}
  function redrawFacility(kind){
    clearFacility(kind);
    if(!facilityState[kind])return;
    const points=DATA.facilities[kind]||[];
    if(!points.length)return;
    const zoom=map.getZoom();
    if(zoom<14)return;
    const bounds=map.getBounds();
    const sw=bounds?bounds.getSW():null;
    const ne=bounds?bounds.getNE():null;
    const south=sw?sw.lat():-90,west=sw?sw.lng():-180;
    const north=ne?ne.lat():90,east=ne?ne.lng():180;
    const visible=[];
    for(const point of points){
      if(point[0]<south||point[0]>north||point[1]<west||point[1]>east)continue;
      visible.push(point);
    }
    const MAX_MARKERS=100;
    let cell=zoom>=19?0.00002:0.035/Math.pow(2,Math.max(0,zoom-10));
    let buckets;
    for(let attempt=0;attempt<6;attempt++){
      buckets=new Map();
      for(const point of visible){
        const key=Math.floor(point[0]/cell)+":"+Math.floor(point[1]/cell);
        let bucket=buckets.get(key);
        if(!bucket){bucket={lat:0,lng:0,count:0,label:point[2]||"",address:point[3]||""};buckets.set(key,bucket)}
        bucket.lat+=point[0];bucket.lng+=point[1];bucket.count++;
      }
      if(buckets.size<=MAX_MARKERS)break;
      cell*=2;
    }
    for(const bucket of buckets.values()){const marker=new naver.maps.Marker({position:new naver.maps.LatLng(bucket.lat/bucket.count,bucket.lng/bucket.count),map,title:bucket.count>1?bucket.count+"개 시설":bucket.label,icon:{content:markerContent(kind,bucket.count),size:new naver.maps.Size(30,26),anchor:new naver.maps.Point(15,13)},zIndex:90});if(bucket.label)naver.maps.Event.addListener(marker,"click",()=>openInfo(marker,kind==="police"&&bucket.count===1?'<b>'+esc(bucket.label)+'</b><br>주소: '+esc(bucket.address):'<b>'+esc(bucket.label)+'</b><br>'+(bucket.count>1?"주변 시설 "+bucket.count+"개":"원본 시설 위치")));groups[kind].push(marker)}}
  function redrawFacilities(){Object.keys(facilityState).forEach(redrawFacility)}
  function initNaverMap(){
    try{
    naver=window.naver;
    status.textContent="네이버 지도와 안전 데이터를 불러오는 중…";
    const focus=DATA.focus||{lat:35.18,lng:128.62,zoom:10,name:"창원시"};map=new naver.maps.Map("changwon-naver-map",{center:new naver.maps.LatLng(focus.lat,focus.lng),zoom:focus.zoom||10,mapTypeControl:true,zoomControl:true,zoomControlOptions:{position:naver.maps.Position.LEFT_CENTER},scaleControl:true});infoWindow=new naver.maps.InfoWindow({borderWidth:0,backgroundColor:"transparent",anchorSize:new naver.maps.Size(12,8)});if((focus.zoom||10)>10)new naver.maps.Marker({map,position:new naver.maps.LatLng(focus.lat,focus.lng),title:focus.name||"검색 위치",zIndex:180});
    let riskOutlineMode=false;
    let restyleRiskGrid=()=>{};
    const risk=addGround(
  DATA.riskImage,
  DATA.riskBounds,
  .9
);

if(risk){
  risk.setMap(null);

  addControl(
    "risk",
    "원본 범죄위험 지도 (경찰청·참고)",
    false,
    v=>{
      risk.setMap(v?map:null);
      riskOutlineMode=v;
      restyleRiskGrid();
    }
  );
}

const safeCells=DATA.safeCells||[];
if(safeCells.length){
  const safeIcon=
    '<svg width="24" height="22" viewBox="0 0 30 28">'+
    '<polygon points="15,2 28,26 2,26" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/>'+
    '<polygon points="15,2 28,26 2,26" fill="rgba(22,163,74,.15)" stroke="#16A34A" stroke-width="3.5" stroke-linejoin="round"/>'+
    '</svg>';
  const safeMarkers=safeCells.map(cell=>{
    const marker=new naver.maps.Marker({
      position:new naver.maps.LatLng(Number(cell.lat),Number(cell.lng)),
      map:null,
      title:"안전요소 3종 충족 (CCTV·보안등·Wi-Fi)",
      icon:{
        content:safeIcon,
        size:new naver.maps.Size(24,22),
        anchor:new naver.maps.Point(12,11)
      },
      zIndex:120
    });
    naver.maps.Event.addListener(marker,"click",()=>openInfo(
      marker,
      '<div style="background:#fff;border:1px solid #cbd5e1;border-radius:10px;'+
      'padding:8px 11px;box-shadow:0 3px 12px rgba(15,23,42,.18);white-space:nowrap">'+
      '<b style="color:#15803d">△ 안전요소 3종 충족</b><br>'+
      'CCTV·보안등·Wi-Fi가 모두 있는 100m 격자<br>'+
      '<span style="color:#64748b;font-size:11px">부족 시설이 없어 설치 우선순위 대상이 아님</span>'+
      '</div>'
    ));
    return marker;
  });

  addControl(
    "safe",
    "안전요소 3종 충족 격자 (△)",
    false,
    v=>setObjects(safeMarkers,v)
  );
}

const colabRiskGrid=DATA.colabRiskGrid&&DATA.colabRiskGrid.features
  &&DATA.colabRiskGrid.features.length?DATA.colabRiskGrid:null;

if(colabRiskGrid){
  const riskLayer=new naver.maps.Data({map});
  riskLayer.addGeoJson(colabRiskGrid);
  const riskGridStyle=feature=>{
    const pct=Number(feature.getProperty("risk_pct")||0);
    const color=pct>=25?"#991B1B":pct>=10?"#EF4444":"#F87171";
    if(riskOutlineMode){
      return{
        strokeColor:pct>=25?"#7F1D1D":pct>=10?"#DC2626":"#F87171",
        strokeWeight:pct>=25?4:pct>=10?2.5:1.5,
        strokeOpacity:pct>=25?1:.9,
        strokeStyle:pct>=10?"solid":"shortdash",
        fillColor:"#7F1D1D",
        fillOpacity:pct>=25?.12:0,
        clickable:false,
        zIndex:pct>=25?142:pct>=10?141:140
      };
    }
    return{
      strokeColor:color,
      strokeWeight:0,
      strokeOpacity:0,
      fillColor:pct>=10?color:"#FCA5A5",
      fillOpacity:pct>=25?.6:pct>=10?.45:.3,
      clickable:false,
      zIndex:140
    };
  };
  riskLayer.setStyle(riskGridStyle);
  restyleRiskGrid=()=>riskLayer.setStyle(riskGridStyle);

  let riskGridEnabled=true;
  let riskGridShown=null;
  const updateRiskGrid=force=>{
    const show=riskGridEnabled&&map.getZoom()>=13;
    if(!force&&show===riskGridShown)return;
    riskGridShown=show;
    riskLayer.setMap(null);
    if(show)riskLayer.setMap(map);
  };
  naver.maps.Event.once(map,"idle",()=>updateRiskGrid(true));
  setTimeout(()=>updateRiskGrid(true),800);
  naver.maps.Event.addListener(map,"zoom_changed",()=>updateRiskGrid(false));

  addControl(
    "grid",
    "범죄 고위험 면적 비율 (100m 격자)",
    true,
    v=>{
      riskGridEnabled=v;
      updateRiskGrid(true);
    }
  );
}else{
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
}

const outer=makeDataLayer(
  DATA.outerBoundary,
  {
    strokeColor:"#475569",
    strokeWeight:3,
    strokeOpacity:0,
    fillColor:"#475569",
    fillOpacity:.01,
    clickable:false,
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
      strokeWeight:3,
      strokeOpacity:1,
      fillColor:color,
      fillOpacity:.018,
      clickable:false,
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
    const labels={cctv:"원본 방범용 CCTV",light:"원본 보안등",wifi:"원본 공공 Wi-Fi",police:"원본 지구대·파출소"};const swatchSymbols={cctv:"C",light:"L",wifi:"W",police:"P"};for(const kind of ["cctv","light","wifi","police"]){if((DATA.facilities[kind]||[]).length){facilityState[kind]=false;addControl(kind,labels[kind],false,v=>{facilityState[kind]=v;redrawFacility(kind)});const layerRows=document.getElementById("layer-items").children;const swatch=document.createElement("span");swatch.className="facility-marker "+kind;swatch.style.cssText="min-width:18px;height:18px;padding:0 3px;margin-left:auto;font-size:9px;border-width:1px";swatch.textContent=swatchSymbols[kind];layerRows[layerRows.length-1].appendChild(swatch)}}
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
    facility_points: list[dict] | None = None,
) -> str:
    """TOP10 위치 모달용 간단한 NAVER 지도를 생성합니다."""
    feature_json = json.dumps(
        feature,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    facility_json = json.dumps(
        facility_points or [],
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
#top10-facility-legend {
    position: absolute;
    z-index: 900;
    top: 12px;
    right: 12px;
    min-width: 135px;
    padding: 8px 9px;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.96);
    box-shadow: 0 3px 12px rgba(15, 23, 42, 0.14);
    color: #334155;
    font-size: 11px;
}

.top10-legend-title {
    margin-bottom: 5px;
    color: #0f172a;
    font-size: 12px;
    font-weight: 900;
}

.top10-legend-row {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-top: 4px;
    white-space: nowrap;
}

.top10-legend-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 21px;
    height: 21px;
    border-radius: 50%;
    flex: 0 0 21px;
    font-size: 12px;
}

.top10-legend-icon.cctv {
    border: 2px solid #991b1b;
    background: #dc2626;
}

.top10-legend-icon.light { border: 2px solid #b45309; background: #f59e0b; }
.top10-legend-icon.wifi { border: 2px solid #1d4ed8; background: #3b82f6; }
.top10-legend-icon.police { border: 2px solid #1e3a8a; background: #1e40af; }

.top10-legend-divider {
    margin: 7px 0 5px 0;
    border-top: 1px solid #e2e8f0;
}

.top10-range-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 4px;
    color: #64748b;
    font-size: 10px;
    font-weight: 700;
}

.top10-range-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex: 0 0 9px;
}

.top10-range-dot.strong {
    background: #334155;
    border: 1px solid #0f172a;
}

.top10-range-dot.soft {
    background: #e2e8f0;
    border: 1px solid #64748b;
}
</style>

<div id="top10-location-shell">
    <div id="top10-location-map"></div>

    <div id="top10-facility-legend">
        <div class="top10-legend-title">
            주변 안전시설
        </div>

        <div class="top10-legend-row">
            <span class="top10-legend-icon cctv">📹</span>
            <span>CCTV</span>
        </div>

        <div class="top10-legend-row">
            <span class="top10-legend-icon light">💡</span>
            <span>보안등</span>
        </div>

        <div class="top10-legend-row">
            <span class="top10-legend-icon wifi">📶</span>
            <span>Wi-Fi</span>
        </div>

        <div class="top10-legend-row">
            <span class="top10-legend-icon police">🛡</span>
            <span>파출소</span>
        </div>

        <div class="top10-legend-divider"></div>

        <div class="top10-range-row">
            <span class="top10-range-dot strong"></span>
            <span>진한색 · 분석 기준 내 (TOP10 영역 안)</span>
        </div>

        <div class="top10-range-row">
            <span class="top10-range-dot soft"></span>
            <span>연한색 · 300m 주변 참고</span>
        </div>
    </div>
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
    const FACILITY_POINTS = __FACILITY_POINTS__;
    const FACILITY_STYLES = {
        cctv:   { name: "CCTV",   icon: "📹", strong: ["#DC2626", "#991B1B"], soft: ["#FECACA", "#DC2626"], size: 24 },
        light:  { name: "보안등", icon: "💡", strong: ["#F59E0B", "#B45309"], soft: ["#FEF3C7", "#D97706"], size: 20 },
        wifi:   { name: "Wi-Fi",  icon: "📶", strong: ["#3B82F6", "#1D4ED8"], soft: ["#DBEAFE", "#2563EB"], size: 22 },
        police: { name: "파출소", icon: "🛡", strong: ["#1E40AF", "#1E3A8A"], soft: ["#C7D2FE", "#1E3A8A"], size: 26 }
    };

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

            FACILITY_POINTS.forEach(function (point) {
                const style = FACILITY_STYLES[point.type] || FACILITY_STYLES.cctv;
                const position = new naver.maps.LatLng(
                    Number(point.lat),
                    Number(point.lng)
                );
                const inAnalysisRange = Boolean(point.in_analysis_range);
                const colors = inAnalysisRange ? style.strong : style.soft;
                const size = style.size;
                const rangeLabel = point.type === "police"
                    ? "참고용 · 최종 취약점수 미반영"
                    : (inAnalysisRange
                        ? "분석 기준 내 (TOP10 영역 안)"
                        : "300m 주변 참고 (영역 밖)");

                const marker = new naver.maps.Marker({
                    map: map,
                    position: position,
                    title: style.name + " · " + rangeLabel,
                    zIndex: inAnalysisRange ? 175 : 165,
                    icon: {
                        content:
                            '<div style="' +
                            'display:flex;align-items:center;justify-content:center;' +
                            'width:' + size + 'px;height:' + size + 'px;' +
                            'border-radius:50%;' +
                            'border:2px solid ' + colors[1] + ';' +
                            'background:' + colors[0] + ';' +
                            'opacity:' + (inAnalysisRange ? '1' : '0.85') + ';' +
                            'font-size:' + Math.round(size * 0.52) + 'px;' +
                            'box-shadow:0 1px 5px rgba(0,0,0,.28)">' +
                            style.icon +
                            '</div>',
                        size: new naver.maps.Size(size, size),
                        anchor: new naver.maps.Point(size / 2, size / 2)
                    }
                });

                const label = String(point.label || "")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;");

                const info = new naver.maps.InfoWindow({
                    content:
                        '<div style="padding:9px 11px;font-size:12px;line-height:1.55">' +
                        '<b>' + style.icon + ' ' + style.name + '</b><br>' +
                        rangeLabel + '<br>' +
                        '중심점 거리 · ' + Number(point.distance).toFixed(1) + 'm' +
                        (label ? '<br>' + label : '') +
                        '</div>'
                });

                naver.maps.Event.addListener(marker, "click", function () {
                    info.open(map, marker);
                });
            });

            if (FACILITY_POINTS.length > 0) {
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
        .replace("__FACILITY_POINTS__", facility_json)
        .replace("__CLIENT_ID__", safe_client_id)
    )
