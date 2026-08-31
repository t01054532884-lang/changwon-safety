import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="창원시 안전지도",
    layout="wide"
)

st.title("창원시 안전지도")
st.write("창원시 안전취약지역 분석을 위한 테스트 지도입니다.")

m = folium.Map(
    location=[35.2279, 128.6811],
    zoom_start=11
)

st_folium(
    m,
    width=1200,
    height=700
)