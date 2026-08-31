import json
from html import escape
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from folium.plugins import FastMarkerCluster, MarkerCluster
from streamlit_folium import st_folium


BASE_DIR = Path(__file__).resolve().parent
CCTV_FILE = BASE_DIR / "data" / "cctv_coordinates.csv"
CHANGWON_BOUNDARY_FILE = BASE_DIR / "data" / "changwon_boundary.geojson"
GIMHAE_BOUNDARY_FILE = BASE_DIR / "data" / "gimhae_boundary.geojson"
TONGYEONG_BOUNDARY_FILE = BASE_DIR / "data" / "tongyeong_boundary.geojson"
PEDESTRIAN_LIGHT_FILE = BASE_DIR / "data" / "nonroad_lights.json"


@st.cache_data(show_spinner=False)
def load_cctv_data(file_path: Path) -> pd.DataFrame:
    """좌표 변환이 완료된 CCTV CSV를 읽고 유효한 좌표만 반환합니다."""
    dataframe = pd.read_csv(file_path)

    required_columns = {"설치장소", "latitude", "longitude"}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CCTV CSV에 필요한 열이 없습니다: {missing}")

    dataframe["latitude"] = pd.to_numeric(
        dataframe["latitude"], errors="coerce"
    )
    dataframe["longitude"] = pd.to_numeric(
        dataframe["longitude"], errors="coerce"
    )

    return dataframe.dropna(subset=["latitude", "longitude"]).copy()


@st.cache_data(show_spinner=False)
def load_geojson(file_path: Path) -> dict:
    """행정경계 GeoJSON을 읽습니다."""
    return json.loads(file_path.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_pedestrian_light_data(file_path: Path) -> dict:
    """공개 관리시스템에서 받은 비차도 조명 좌표를 읽습니다."""
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    records = []

    for record in payload.get("records", []):
        try:
            latitude = float(record["latitude"])
            longitude = float(record["longitude"])
        except (KeyError, TypeError, ValueError):
            continue

        if not (34.8 <= latitude <= 35.6 and 128.1 <= longitude <= 129.0):
            continue

        records.append(record)

    payload["records"] = records
    return payload


def add_boundary_layer(
    map_object: folium.Map,
    file_path: Path,
    layer_name: str,
    line_color: str,
) -> bool:
    """비교할 도시를 쉽게 추가할 수 있는 행정경계 레이어를 만듭니다."""
    if not file_path.exists():
        return False

    boundary_data = load_geojson(file_path)
    folium.GeoJson(
        data=boundary_data,
        name=layer_name,
        overlay=True,
        control=True,
        show=True,
        style_function=lambda _: {
            "color": line_color,
            "weight": 5,
            "opacity": 0.95,
            "fillColor": line_color,
            "fillOpacity": 0.025,
        },
        highlight_function=lambda _: {
            "color": line_color,
            "weight": 7,
            "opacity": 1.0,
            "fillOpacity": 0.06,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["name"],
            aliases=["행정구역:"],
            labels=True,
            sticky=False,
        ),
    ).add_to(map_object)
    return True


def popup_html(row: pd.Series) -> str:
    """지도 팝업에 표시할 CCTV 정보를 안전한 HTML로 만듭니다."""
    def value(column: str, default: str = "정보 없음") -> str:
        cell = row.get(column, default)
        if pd.isna(cell) or str(cell).strip() == "":
            cell = default
        return escape(str(cell))

    camera_number = value("카메라번호", "-")
    return f"""
    <div style="width: 300px; font-size: 14px; line-height: 1.55;">
        <b>방범용 CCTV</b><br>
        <b>설치장소:</b> {value('설치장소')}<br>
        <b>카메라 번호:</b> {camera_number}<br>
        <b>설치목적:</b> {value('설치목적')}<br>
        <b>촬영범위:</b> {value('촬영범위')}<br>
        <b>촬영시간:</b> {value('촬영시간')}
    </div>
    """


st.set_page_config(
    page_title="창원시 안전지도",
    layout="wide",
)

st.title("창원시 안전지도")
st.write("창원시 방범용 CCTV 위치를 확인할 수 있습니다.")
st.caption("행정경계 데이터: © OpenStreetMap contributors (참고용)")

map_views = {
    "창원시 중심": {"location": [35.2279, 128.6811], "zoom": 11},
    "김해시 중심": {"location": [35.2500, 128.8800], "zoom": 11},
    "통영시 중심": {"location": [34.8500, 128.4300], "zoom": 10},
    "세 도시 비교": {"location": [34.9000, 128.6000], "zoom": 8},
}
selected_map_view = st.selectbox(
    "지도 중심",
    options=list(map_views),
    index=0,
)
map_view = map_views[selected_map_view]

map_object = folium.Map(
    location=map_view["location"],
    zoom_start=map_view["zoom"],
    tiles="OpenStreetMap",
    control_scale=True,
    prefer_canvas=True,
)
show_changwon_facilities = selected_map_view == "창원시 중심"

add_boundary_layer(
    map_object=map_object,
    file_path=CHANGWON_BOUNDARY_FILE,
    layer_name="창원시 행정경계",
    line_color="#7C3AED",
)
add_boundary_layer(
    map_object=map_object,
    file_path=GIMHAE_BOUNDARY_FILE,
    layer_name="김해시 행정경계",
    line_color="#16A34A",
)
add_boundary_layer(
    map_object=map_object,
    file_path=TONGYEONG_BOUNDARY_FILE,
    layer_name="통영시 행정경계",
    line_color="#DC2626",
)

map_object.get_root().html.add_child(
    folium.Element(
        """
        <style>
        .cctv-small-cluster {
            background: #DC2626;
            border: 3px solid #7F1D1D;
            border-radius: 50%;
            box-shadow: 0 0 0 3px rgba(254, 202, 202, 0.75);
        }
        .streetlight-cluster {
            display: flex;
            align-items: center;
            justify-content: center;
            background: #FACC15;
            border: 3px solid #A16207;
            border-radius: 50%;
            color: #422006;
            font-size: 12px;
            font-weight: 800;
            box-shadow: 0 0 0 3px rgba(254, 240, 138, 0.7);
        }
        .streetlight-div-icon {
            background: transparent !important;
            border: 0 !important;
        }
        .streetlight-symbol {
            position: relative;
            width: 18px;
            height: 28px;
            filter: drop-shadow(0 1px 1px rgba(66, 32, 6, 0.55));
        }
        .streetlight-glow {
            position: absolute;
            top: 0;
            left: 3px;
            width: 16px;
            height: 15px;
            border-radius: 50%;
            background: rgba(250, 204, 21, 0.5);
            filter: blur(2px);
        }
        .streetlight-head {
            position: absolute;
            top: 3px;
            left: 5px;
            width: 12px;
            height: 7px;
            border: 2px solid #78350F;
            border-radius: 55% 55% 45% 45%;
            background: #FDE047;
            transform: rotate(-8deg);
        }
        .streetlight-arm {
            position: absolute;
            top: 8px;
            left: 7px;
            width: 8px;
            height: 3px;
            border-radius: 2px;
            background: #78350F;
            transform: rotate(-25deg);
            transform-origin: left center;
        }
        .streetlight-post {
            position: absolute;
            top: 9px;
            left: 7px;
            width: 3px;
            height: 17px;
            border-radius: 2px;
            background: #78350F;
        }
        </style>
        """
    )
)

pedestrian_light_payload = {"records": []}
if show_changwon_facilities and PEDESTRIAN_LIGHT_FILE.exists():
    try:
        pedestrian_light_payload = load_pedestrian_light_data(
            PEDESTRIAN_LIGHT_FILE
        )
    except Exception as error:
        st.error(f"보행조명 데이터를 읽지 못했습니다: {error}")

pedestrian_lights = pedestrian_light_payload["records"]
if pedestrian_lights:
    coverage = "·".join(pedestrian_light_payload.get("coverage", []))
    st.caption(
        f"보행조명 데이터 제공 범위: {coverage} 공개 관리시스템 "
        "(차도 가로등 제외)"
    )

    streetlight_markers = [
        [
            record["latitude"],
            record["longitude"],
            record.get("manage_no") or "정보 없음",
            record.get("location") or "정보 없음",
            record.get("light_type") or "보행조명",
            record.get("district") or "",
        ]
        for record in pedestrian_lights
    ]

    streetlight_callback = """
    function(row) {
        if (!window.changwonPedestrianLightIcon) {
            window.changwonPedestrianLightIcon = L.divIcon({
                html: '<div class="streetlight-symbol">' +
                      '<span class="streetlight-glow"></span>' +
                      '<span class="streetlight-head"></span>' +
                      '<span class="streetlight-arm"></span>' +
                      '<span class="streetlight-post"></span></div>',
                className: 'streetlight-div-icon',
                iconSize: [18, 28],
                iconAnchor: [8, 26],
                popupAnchor: [1, -24]
            });
        }

        var marker = L.marker([row[0], row[1]], {
            icon: window.changwonPedestrianLightIcon,
            title: row[4] + ' ' + row[2]
        });

        marker.on('click', function() {
            if (!marker.getPopup()) {
                var popup = document.createElement('div');
                popup.style.width = '260px';
                popup.style.fontSize = '14px';
                popup.style.lineHeight = '1.55';

                var heading = document.createElement('b');
                heading.textContent = row[4];
                popup.appendChild(heading);
                popup.appendChild(document.createElement('br'));

                var numberLabel = document.createElement('b');
                numberLabel.textContent = '관리번호: ';
                popup.appendChild(numberLabel);
                popup.appendChild(document.createTextNode(row[2] || '정보 없음'));
                popup.appendChild(document.createElement('br'));

                var addressLabel = document.createElement('b');
                addressLabel.textContent = '주소: ';
                popup.appendChild(addressLabel);
                popup.appendChild(document.createTextNode(row[3] || '정보 없음'));
                popup.appendChild(document.createElement('br'));

                var districtLabel = document.createElement('b');
                districtLabel.textContent = '제공 구: ';
                popup.appendChild(districtLabel);
                popup.appendChild(document.createTextNode(row[5] || '정보 없음'));
                marker.bindPopup(popup);
            }
            marker.openPopup();
        });
        return marker;
    }
    """

    streetlight_cluster_icon = """
    function(cluster) {
        var count = cluster.getChildCount();
        var size = count < 100 ? 32 : count < 1000 ? 38 : 44;
        return L.divIcon({
            html: '<span>' + count.toLocaleString() + '</span>',
            className: 'streetlight-cluster',
            iconSize: new L.Point(size, size)
        });
    }
    """

    FastMarkerCluster(
        data=streetlight_markers,
        callback=streetlight_callback,
        name="보행조명(차도 가로등 제외)",
        overlay=True,
        control=True,
        show=True,
        icon_create_function=streetlight_cluster_icon,
        options={
            "maxClusterRadius": 55,
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": False,
        },
    ).add_to(map_object)

if not show_changwon_facilities:
    pass
elif not CCTV_FILE.exists():
    st.warning(
        "아직 CCTV 좌표 파일이 없습니다. 먼저 `python geocode_cctv.py`를 "
        "실행해 `data/cctv_coordinates.csv`를 만들어 주세요."
    )
else:
    try:
        cctv_data = load_cctv_data(CCTV_FILE)
    except Exception as error:
        st.error(f"CCTV 데이터를 읽지 못했습니다: {error}")
        cctv_data = pd.DataFrame()

    if cctv_data.empty:
        st.warning("지도에 표시할 유효한 CCTV 좌표가 없습니다.")
    else:
        total_count = len(cctv_data)
        unique_location_count = cctv_data[
            ["latitude", "longitude"]
        ].drop_duplicates().shape[0]

        first_column, second_column, third_column = st.columns(3)
        first_column.metric("표시 CCTV", f"{total_count:,}대")
        second_column.metric("좌표 위치", f"{unique_location_count:,}곳")
        third_column.metric("표시 보행조명", f"{len(pedestrian_lights):,}개")

        coverage_group = folium.FeatureGroup(
            name="CCTV 촬영범위 약 100m",
            overlay=True,
            control=True,
            show=True,
        ).add_to(map_object)

        unique_locations = cctv_data.drop_duplicates(
            subset=["latitude", "longitude"]
        )
        for _, location_row in unique_locations.iterrows():
            folium.Circle(
                location=[
                    location_row["latitude"],
                    location_row["longitude"],
                ],
                radius=100,
                color="#2563EB",
                weight=2,
                opacity=0.8,
                dash_array="5, 7",
                fill=True,
                fill_color="#60A5FA",
                fill_opacity=0.05,
                tooltip="CCTV 촬영범위 약 100m",
            ).add_to(coverage_group)

        cluster_icon = """
        function(cluster) {
            var count = cluster.getChildCount();
            if (count <= 3) {
                return L.divIcon({
                    html: '',
                    className: 'cctv-small-cluster',
                    iconSize: new L.Point(18, 18)
                });
            }

            var size = count < 10 ? 'small' :
                       count < 100 ? 'medium' : 'large';
            return L.divIcon({
                html: '<div><span>' + count + '</span></div>',
                className: 'marker-cluster marker-cluster-' + size,
                iconSize: new L.Point(40, 40)
            });
        }
        """

        marker_cluster = MarkerCluster(
            name="방범용 CCTV",
            overlay=True,
            control=True,
            show=True,
            icon_create_function=cluster_icon,
            options={
                "disableClusteringAtZoom": 15,
                "spiderfyOnMaxZoom": True,
                "showCoverageOnHover": False,
            },
        ).add_to(map_object)

        for _, row in cctv_data.iterrows():
            camera_number = row.get("카메라번호", "")
            tooltip = "방범용 CCTV"
            if pd.notna(camera_number) and str(camera_number).strip():
                tooltip = f"방범용 CCTV #{camera_number}"

            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=7,
                color="#7F1D1D",
                weight=3,
                fill=True,
                fill_color="#DC2626",
                fill_opacity=1.0,
                tooltip=tooltip,
                popup=folium.Popup(popup_html(row), max_width=340),
            ).add_to(marker_cluster)

folium.LayerControl(collapsed=False).add_to(map_object)

st_folium(
    map_object,
    width=None,
    height=700,
    key=f"changwon-safety-map-{selected_map_view}",
    returned_objects=[],
)
