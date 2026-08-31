from html import escape
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium


BASE_DIR = Path(__file__).resolve().parent
CCTV_FILE = BASE_DIR / "data" / "cctv_coordinates.csv"


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

map_object = folium.Map(
    location=[35.2279, 128.6811],
    zoom_start=11,
    tiles="OpenStreetMap",
    control_scale=True,
)

if not CCTV_FILE.exists():
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

        first_column, second_column = st.columns(2)
        first_column.metric("표시 CCTV", f"{total_count:,}대")
        second_column.metric("좌표 위치", f"{unique_location_count:,}곳")

        marker_cluster = MarkerCluster(
            name="방범용 CCTV",
            overlay=True,
            control=True,
            show=True,
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
    key="changwon-safety-map",
    returned_objects=[],
)
