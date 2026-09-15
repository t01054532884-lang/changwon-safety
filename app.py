import json
import math
import os
from datetime import datetime, timedelta
from io import BytesIO
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import folium
import numpy as np
import pandas as pd
import streamlit as st
from folium.map import Layer
from jinja2 import Template
from PIL import Image, ImageDraw
from streamlit_folium import st_folium


BASE_DIR = Path(__file__).resolve().parent
CCTV_FILE = BASE_DIR / "data" / "cctv_coordinates.xlsx"
WIFI_FILE = BASE_DIR / "data" / "wifi_data.csv"
CHANGWON_BOUNDARY_FILE = BASE_DIR / "data" / "changwon_boundary.geojson"
CHANGWON_DISTRICTS_BOUNDARY_FILE = (
    BASE_DIR / "data" / "changwon_districts_boundary.geojson"
)
PEDESTRIAN_LIGHT_FILE = BASE_DIR / "data" / "nonroad_lights.json"
ANALYSIS_GRID_SIZE = 100
RISK_RASTER_SIZE = 1024
CHANGWON_BOUNDS = (34.75, 128.10, 35.55, 129.00)
PEDESTRIAN_ROUTER_URL = (
    "https://routing.openstreetmap.de/routed-foot/route/v1/driving"
)
DISTRICT_COLORS = {
    "의창구": "#2563EB",
    "성산구": "#F59E0B",
    "마산합포구": "#DC2626",
    "마산회원구": "#16A34A",
    "진해구": "#7C3AED",
}
SAFEMAP_RISK_PROFILES = {
    "노인 버전": {
        "title": "노인 대상 범죄주의구간",
        "url": "https://www.safemap.go.kr/openapi2/IF_0082_WMS",
        "layer": "A2SM_ODBLRCRMNLHSPOT_ODSN",
        "style": "A2SM_OdblrCrmnlHspot_Odsn",
    },
    "어린이 버전": {
        "title": "어린이 대상 범죄주의구간",
        "url": "https://www.safemap.go.kr/openapi2/IF_0081_WMS",
        "layer": "A2SM_ODBLRCRMNLHSPOT_KID",
        "style": "A2SM_OdblrCrmnlHspot_Kid",
    },
}


class ThresholdLightLayer(Layer):
    """10개를 초과할 때만 군집으로 표시하는 보행조명 레이어."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = (function() {
            var map = {{ this._parent.get_name() }};
            var layer = L.layerGroup();
            var data = {{ this.data | tojson }};
            var minimumClusterSize = {{ this.minimum_cluster_size }};
            var cellSize = {{ this.cell_size }};
            var redrawTimer = null;

            function lightIcon() {
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
                return window.changwonPedestrianLightIcon;
            }

            function makeLightMarker(row) {
                var marker = L.marker([row[0], row[1]], {
                    icon: lightIcon(),
                    title: '보행조명 · ' + row[2]
                });

                marker.on('click', function() {
                    if (!marker.getPopup()) {
                        var popup = document.createElement('div');
                        popup.style.width = '260px';
                        popup.style.fontSize = '14px';
                        popup.style.lineHeight = '1.55';

                        var fields = [
                            ['보행조명', ''],
                            ['제공 구: ', row[2]],
                            [
                                '좌표: ',
                                row[0].toFixed(6) + ', ' +
                                row[1].toFixed(6)
                            ]
                        ];

                        fields.forEach(function(field, index) {
                            var label = document.createElement('b');
                            label.textContent = field[0];
                            popup.appendChild(label);
                            if (field[1]) {
                                popup.appendChild(
                                    document.createTextNode(
                                        field[1] || '정보 없음'
                                    )
                                );
                            }
                            if (index < fields.length - 1) {
                                popup.appendChild(document.createElement('br'));
                            }
                        });
                        marker.bindPopup(popup);
                    }
                    marker.openPopup();
                });
                return marker;
            }

            function makeCluster(rows) {
                var latitudeTotal = 0;
                var longitudeTotal = 0;
                var clusterBounds = [];

                rows.forEach(function(row) {
                    latitudeTotal += row[0];
                    longitudeTotal += row[1];
                    clusterBounds.push([row[0], row[1]]);
                });

                var count = rows.length;
                var center = [
                    latitudeTotal / count,
                    longitudeTotal / count
                ];
                var size = count < 100 ? 32 : count < 1000 ? 38 : 44;
                var icon = L.divIcon({
                    html: '<span>' + count.toLocaleString() + '</span>',
                    className: 'streetlight-cluster',
                    iconSize: new L.Point(size, size)
                });
                var marker = L.marker(center, {
                    icon: icon,
                    title: '보행조명 ' + count.toLocaleString() + '개'
                });

                marker.on('click', function() {
                    var bounds = L.latLngBounds(clusterBounds);
                    var targetZoom = Math.min(map.getZoom() + 2, 18);
                    if (bounds.getNorthEast().equals(bounds.getSouthWest())) {
                        map.setView(center, targetZoom);
                    } else {
                        map.fitBounds(bounds, {
                            padding: [35, 35],
                            maxZoom: targetZoom
                        });
                    }
                });
                return marker;
            }

            function redraw() {
                redrawTimer = null;
                if (!map.hasLayer(layer)) {
                    return;
                }

                layer.clearLayers();
                var bounds = map.getBounds().pad(0.15);
                var buckets = {};

                data.forEach(function(row) {
                    var latLng = L.latLng(row[0], row[1]);
                    if (!bounds.contains(latLng)) {
                        return;
                    }

                    var point = map.latLngToContainerPoint(latLng);
                    var key = Math.floor(point.x / cellSize) + ':' +
                              Math.floor(point.y / cellSize);
                    if (!buckets[key]) {
                        buckets[key] = [];
                    }
                    buckets[key].push(row);
                });

                Object.keys(buckets).forEach(function(key) {
                    var rows = buckets[key];
                    if (rows.length > minimumClusterSize) {
                        makeCluster(rows).addTo(layer);
                    } else {
                        rows.forEach(function(row) {
                            makeLightMarker(row).addTo(layer);
                        });
                    }
                });
            }

            function scheduleRedraw() {
                if (redrawTimer !== null) {
                    window.clearTimeout(redrawTimer);
                }
                redrawTimer = window.setTimeout(redraw, 40);
            }

            map.on('zoomend moveend resize', scheduleRedraw);
            layer.on('add', scheduleRedraw);
            {% if this.show %}
            layer.addTo(map);
            {% endif %}
            scheduleRedraw();
            return layer;
        })();
        {% endmacro %}
        """
    )

    def __init__(
        self,
        data: list[list],
        name: str,
        minimum_cluster_size: int = 10,
        cell_size: int = 55,
        show: bool = True,
    ) -> None:
        super().__init__(name=name, overlay=True, control=True, show=show)
        self.data = data
        self.minimum_cluster_size = minimum_cluster_size
        self.cell_size = cell_size


class ThresholdCctvLayer(Layer):
    """카메라 합계가 10대를 초과할 때만 빨간 군집으로 표시합니다."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = (function() {
            var map = {{ this._parent.get_name() }};
            var layer = L.layerGroup();
            var data = {{ this.data | tojson }};
            var minimumClusterSize = {{ this.minimum_cluster_size }};
            var cellSize = {{ this.cell_size }};
            var redrawTimer = null;

            function cctvIcon() {
                if (!window.changwonCctvIcon) {
                    window.changwonCctvIcon = L.divIcon({
                        html: '<div class="cctv-camera-symbol">' +
                              '<span class="cctv-camera-lens"></span>' +
                              '<span class="cctv-camera-arm"></span></div>',
                        className: 'cctv-div-icon',
                        iconSize: [24, 24],
                        iconAnchor: [12, 19],
                        popupAnchor: [0, -18]
                    });
                }
                return window.changwonCctvIcon;
            }

            function addPopupField(popup, labelText, value, addBreak) {
                var label = document.createElement('b');
                label.textContent = labelText;
                popup.appendChild(label);
                popup.appendChild(
                    document.createTextNode(value || '정보 없음')
                );
                if (addBreak) {
                    popup.appendChild(document.createElement('br'));
                }
            }

            function makeCctvMarker(row) {
                var marker = L.marker([row[0], row[1]], {
                    icon: cctvIcon(),
                    title: '방범용 CCTV ' + row[2].toLocaleString() + '대'
                });

                marker.on('click', function() {
                    if (!marker.getPopup()) {
                        var popup = document.createElement('div');
                        popup.style.width = '290px';
                        popup.style.fontSize = '14px';
                        popup.style.lineHeight = '1.55';

                        var heading = document.createElement('b');
                        heading.textContent = '방범용 CCTV';
                        popup.appendChild(heading);
                        popup.appendChild(document.createElement('br'));
                        addPopupField(
                            popup,
                            '카메라 수: ',
                            row[2].toLocaleString() + '대',
                            true
                        );
                        addPopupField(popup, '주소: ', row[3], true);
                        addPopupField(popup, '설치 목적: ', row[4], true);
                        addPopupField(popup, '화소 수: ', row[5], true);
                        addPopupField(popup, '촬영 방면: ', row[6], false);
                        marker.bindPopup(popup);
                    }
                    marker.openPopup();
                });
                return marker;
            }

            function cameraTotal(rows) {
                return rows.reduce(function(total, row) {
                    return total + row[2];
                }, 0);
            }

            function makeCluster(rows) {
                var latitudeTotal = 0;
                var longitudeTotal = 0;
                var clusterBounds = [];

                rows.forEach(function(row) {
                    latitudeTotal += row[0];
                    longitudeTotal += row[1];
                    clusterBounds.push([row[0], row[1]]);
                });

                var count = cameraTotal(rows);
                var center = [
                    latitudeTotal / rows.length,
                    longitudeTotal / rows.length
                ];
                var size = count < 100 ? 32 : count < 1000 ? 38 : 44;
                var icon = L.divIcon({
                    html: '<span>' + count.toLocaleString() + '</span>',
                    className: 'cctv-cluster',
                    iconSize: new L.Point(size, size)
                });
                var marker = L.marker(center, {
                    icon: icon,
                    title: '방범용 CCTV ' + count.toLocaleString() + '대'
                });

                marker.on('click', function() {
                    var bounds = L.latLngBounds(clusterBounds);
                    var targetZoom = Math.min(map.getZoom() + 2, 18);
                    if (bounds.getNorthEast().equals(bounds.getSouthWest())) {
                        map.setView(center, targetZoom);
                    } else {
                        map.fitBounds(bounds, {
                            padding: [35, 35],
                            maxZoom: targetZoom
                        });
                    }
                });
                return marker;
            }

            function redraw() {
                redrawTimer = null;
                if (!map.hasLayer(layer)) {
                    return;
                }

                layer.clearLayers();
                var bounds = map.getBounds().pad(0.15);
                var buckets = {};

                data.forEach(function(row) {
                    var latLng = L.latLng(row[0], row[1]);
                    if (!bounds.contains(latLng)) {
                        return;
                    }

                    var point = map.latLngToContainerPoint(latLng);
                    var key = Math.floor(point.x / cellSize) + ':' +
                              Math.floor(point.y / cellSize);
                    if (!buckets[key]) {
                        buckets[key] = [];
                    }
                    buckets[key].push(row);
                });

                Object.keys(buckets).forEach(function(key) {
                    var rows = buckets[key];
                    if (cameraTotal(rows) > minimumClusterSize) {
                        makeCluster(rows).addTo(layer);
                    } else {
                        rows.forEach(function(row) {
                            makeCctvMarker(row).addTo(layer);
                        });
                    }
                });
            }

            function scheduleRedraw() {
                if (redrawTimer !== null) {
                    window.clearTimeout(redrawTimer);
                }
                redrawTimer = window.setTimeout(redraw, 40);
            }

            map.on('zoomend moveend resize', scheduleRedraw);
            layer.on('add', scheduleRedraw);
            {% if this.show %}
            layer.addTo(map);
            {% endif %}
            scheduleRedraw();
            return layer;
        })();
        {% endmacro %}
        """
    )

    def __init__(
        self,
        data: list[list],
        name: str,
        minimum_cluster_size: int = 10,
        cell_size: int = 55,
        show: bool = True,
    ) -> None:
        super().__init__(name=name, overlay=True, control=True, show=show)
        self.data = data
        self.minimum_cluster_size = minimum_cluster_size
        self.cell_size = cell_size


class VisibleCctvCoverageLayer(Layer):
    """확대 시 현재 화면에 있는 CCTV의 100m 촬영범위만 그립니다."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = (function() {
            var map = {{ this._parent.get_name() }};
            var layer = L.layerGroup();
            var data = {{ this.data | tojson }};
            var minimumZoom = {{ this.minimum_zoom }};
            var redrawTimer = null;

            function redraw() {
                redrawTimer = null;
                layer.clearLayers();
                if (!map.hasLayer(layer) || map.getZoom() < minimumZoom) {
                    return;
                }

                var bounds = map.getBounds().pad(0.1);
                data.forEach(function(row) {
                    var latLng = L.latLng(row[0], row[1]);
                    if (!bounds.contains(latLng)) {
                        return;
                    }
                    L.circle(latLng, {
                        radius: 100,
                        color: '#2563EB',
                        weight: 2,
                        opacity: 0.8,
                        dashArray: '5, 7',
                        fill: true,
                        fillColor: '#60A5FA',
                        fillOpacity: 0.05,
                        interactive: false
                    }).addTo(layer);
                });
            }

            function scheduleRedraw() {
                if (redrawTimer !== null) {
                    window.clearTimeout(redrawTimer);
                }
                redrawTimer = window.setTimeout(redraw, 40);
            }

            map.on('zoomend moveend resize', scheduleRedraw);
            layer.on('add', scheduleRedraw);
            {% if this.show %}
            layer.addTo(map);
            {% endif %}
            scheduleRedraw();
            return layer;
        })();
        {% endmacro %}
        """
    )

    def __init__(
        self,
        data: list[list],
        name: str,
        minimum_zoom: int = 14,
        show: bool = True,
    ) -> None:
        super().__init__(name=name, overlay=True, control=True, show=show)
        self.data = data
        self.minimum_zoom = minimum_zoom


class ThresholdWifiLayer(Layer):
    """와이파이 합계가 10개를 초과할 때만 연한 파란 군집으로 표시합니다."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = (function() {
            var map = {{ this._parent.get_name() }};
            var layer = L.layerGroup();
            var data = {{ this.data | tojson }};
            var minimumClusterSize = {{ this.minimum_cluster_size }};
            var cellSize = {{ this.cell_size }};
            var redrawTimer = null;

            function wifiIcon() {
                if (!window.changwonWifiIcon) {
                    window.changwonWifiIcon = L.divIcon({
                        html: '<div class="wifi-symbol">' +
                              '<span class="wifi-wave wifi-wave-outer"></span>' +
                              '<span class="wifi-wave wifi-wave-middle"></span>' +
                              '<span class="wifi-dot"></span></div>',
                        className: 'wifi-div-icon',
                        iconSize: [26, 26],
                        iconAnchor: [13, 13],
                        popupAnchor: [0, -13]
                    });
                }
                return window.changwonWifiIcon;
            }

            function addPopupField(popup, labelText, value, addBreak) {
                var label = document.createElement('b');
                label.textContent = labelText;
                popup.appendChild(label);
                popup.appendChild(
                    document.createTextNode(value || '정보 없음')
                );
                if (addBreak) {
                    popup.appendChild(document.createElement('br'));
                }
            }

            function makeWifiMarker(row) {
                var marker = L.marker([row[0], row[1]], {
                    icon: wifiIcon(),
                    title: '공공 와이파이 ' + row[2].toLocaleString() + '개'
                });

                marker.on('click', function() {
                    if (!marker.getPopup()) {
                        var popup = document.createElement('div');
                        popup.style.width = '300px';
                        popup.style.fontSize = '14px';
                        popup.style.lineHeight = '1.55';

                        var heading = document.createElement('b');
                        heading.textContent = '공공 와이파이';
                        popup.appendChild(heading);
                        popup.appendChild(document.createElement('br'));
                        addPopupField(popup, '설치 수: ', row[2] + '개', true);
                        addPopupField(popup, '설치 장소: ', row[3], true);
                        addPopupField(popup, '장소 상세: ', row[4], true);
                        addPopupField(popup, '시설 구분: ', row[5], true);
                        addPopupField(popup, 'SSID: ', row[6], true);
                        addPopupField(popup, '서비스 제공사: ', row[7], true);
                        addPopupField(popup, '주소: ', row[8], true);
                        addPopupField(popup, '관리 기관: ', row[9], false);
                        marker.bindPopup(popup);
                    }
                    marker.openPopup();
                });
                return marker;
            }

            function wifiTotal(rows) {
                return rows.reduce(function(total, row) {
                    return total + row[2];
                }, 0);
            }

            function makeCluster(rows) {
                var latitudeTotal = 0;
                var longitudeTotal = 0;
                var clusterBounds = [];

                rows.forEach(function(row) {
                    latitudeTotal += row[0];
                    longitudeTotal += row[1];
                    clusterBounds.push([row[0], row[1]]);
                });

                var count = wifiTotal(rows);
                var center = [
                    latitudeTotal / rows.length,
                    longitudeTotal / rows.length
                ];
                var size = count < 100 ? 32 : count < 1000 ? 38 : 44;
                var icon = L.divIcon({
                    html: '<span>' + count.toLocaleString() + '</span>',
                    className: 'wifi-cluster',
                    iconSize: new L.Point(size, size)
                });
                var marker = L.marker(center, {
                    icon: icon,
                    title: '공공 와이파이 ' + count.toLocaleString() + '개'
                });

                marker.on('click', function() {
                    var bounds = L.latLngBounds(clusterBounds);
                    var targetZoom = Math.min(map.getZoom() + 2, 18);
                    if (bounds.getNorthEast().equals(bounds.getSouthWest())) {
                        map.setView(center, targetZoom);
                    } else {
                        map.fitBounds(bounds, {
                            padding: [35, 35],
                            maxZoom: targetZoom
                        });
                    }
                });
                return marker;
            }

            function redraw() {
                redrawTimer = null;
                if (!map.hasLayer(layer)) {
                    return;
                }

                layer.clearLayers();
                var bounds = map.getBounds().pad(0.15);
                var buckets = {};

                data.forEach(function(row) {
                    var latLng = L.latLng(row[0], row[1]);
                    if (!bounds.contains(latLng)) {
                        return;
                    }

                    var point = map.latLngToContainerPoint(latLng);
                    var key = Math.floor(point.x / cellSize) + ':' +
                              Math.floor(point.y / cellSize);
                    if (!buckets[key]) {
                        buckets[key] = [];
                    }
                    buckets[key].push(row);
                });

                Object.keys(buckets).forEach(function(key) {
                    var rows = buckets[key];
                    if (wifiTotal(rows) > minimumClusterSize) {
                        makeCluster(rows).addTo(layer);
                    } else {
                        rows.forEach(function(row) {
                            makeWifiMarker(row).addTo(layer);
                        });
                    }
                });
            }

            function scheduleRedraw() {
                if (redrawTimer !== null) {
                    window.clearTimeout(redrawTimer);
                }
                redrawTimer = window.setTimeout(redraw, 40);
            }

            map.on('zoomend moveend resize', scheduleRedraw);
            layer.on('add', scheduleRedraw);
            {% if this.show %}
            layer.addTo(map);
            {% endif %}
            scheduleRedraw();
            return layer;
        })();
        {% endmacro %}
        """
    )

    def __init__(
        self,
        data: list[list],
        name: str,
        minimum_cluster_size: int = 10,
        cell_size: int = 55,
        show: bool = True,
    ) -> None:
        super().__init__(name=name, overlay=True, control=True, show=show)
        self.data = data
        self.minimum_cluster_size = minimum_cluster_size
        self.cell_size = cell_size


def combine_unique_text(values: pd.Series) -> str:
    """한 좌표에 여러 행이 있을 때 중복 없는 설명 문자열로 합칩니다."""
    unique_values = []
    for value in values:
        if pd.isna(value) or str(value).strip() == "":
            continue
        text = str(value).strip()
        if text not in unique_values:
            unique_values.append(text)
    return " / ".join(unique_values) or "정보 없음"


def get_safemap_service_key() -> str:
    """환경 변수나 Streamlit Secrets에서 생활안전지도 인증키를 읽습니다."""
    environment_key = os.environ.get("SAFEMAP_SERVICE_KEY", "").strip()
    if environment_key:
        return environment_key

    try:
        return str(st.secrets.get("SAFEMAP_SERVICE_KEY", "")).strip()
    except Exception:
        return ""


@st.cache_resource(show_spinner=False)
def load_cctv_data(file_path: Path) -> pd.DataFrame:
    """최신 CCTV 엑셀을 읽고 앱에서 사용할 열을 정리합니다."""
    dataframe = pd.read_excel(file_path, engine="openpyxl")

    required_columns = {
        "소재지도로명주소",
        "소재지지번주소",
        "설치목적구분",
        "카메라대수",
        "카메라화소수",
        "촬영방면정보",
        "WGS84위도",
        "WGS84경도",
    }
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CCTV 엑셀에 필요한 열이 없습니다: {missing}")

    dataframe["latitude"] = pd.to_numeric(
        dataframe["WGS84위도"], errors="coerce"
    )
    dataframe["longitude"] = pd.to_numeric(
        dataframe["WGS84경도"], errors="coerce"
    )
    dataframe["camera_count"] = (
        pd.to_numeric(dataframe["카메라대수"], errors="coerce")
        .fillna(1)
        .clip(lower=1)
        .round()
        .astype(int)
    )
    dataframe["address"] = dataframe["소재지도로명주소"].fillna(
        dataframe["소재지지번주소"]
    )
    dataframe["purpose"] = dataframe["설치목적구분"].fillna("정보 없음")
    dataframe["pixels"] = dataframe["카메라화소수"].fillna("정보 없음")
    dataframe["direction"] = dataframe["촬영방면정보"].fillna("정보 없음")

    valid_coordinates = (
        dataframe["latitude"].between(34.8, 35.6)
        & dataframe["longitude"].between(128.1, 129.0)
    )
    return dataframe.loc[
        valid_coordinates,
        [
            "latitude",
            "longitude",
            "camera_count",
            "address",
            "purpose",
            "pixels",
            "direction",
        ],
    ].copy()


@st.cache_resource(show_spinner=False)
def load_wifi_data(file_path: Path) -> pd.DataFrame:
    """공공 와이파이 CSV를 읽고 유효한 창원시 좌표만 반환합니다."""
    dataframe = pd.read_csv(file_path, encoding="cp949")

    required_columns = {
        "설치장소명",
        "설치장소상세",
        "설치시설구분명",
        "서비스제공사명",
        "와이파이SSID",
        "소재지도로명주소",
        "소재지지번주소",
        "관리기관명",
        "WGS84위도",
        "WGS84경도",
    }
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"와이파이 CSV에 필요한 열이 없습니다: {missing}")

    dataframe["latitude"] = pd.to_numeric(
        dataframe["WGS84위도"], errors="coerce"
    )
    dataframe["longitude"] = pd.to_numeric(
        dataframe["WGS84경도"], errors="coerce"
    )
    dataframe["address"] = (
        dataframe["소재지도로명주소"]
        .replace("", pd.NA)
        .fillna(dataframe["소재지지번주소"])
    )
    dataframe["place"] = dataframe["설치장소명"].fillna("정보 없음")
    dataframe["detail"] = dataframe["설치장소상세"].fillna("정보 없음")
    dataframe["facility"] = dataframe["설치시설구분명"].fillna("정보 없음")
    dataframe["provider"] = dataframe["서비스제공사명"].fillna("정보 없음")
    dataframe["ssid"] = dataframe["와이파이SSID"].fillna("정보 없음")
    dataframe["manager"] = dataframe["관리기관명"].fillna("정보 없음")

    valid_coordinates = (
        dataframe["latitude"].between(34.8, 35.6)
        & dataframe["longitude"].between(128.1, 129.0)
    )
    return dataframe.loc[
        valid_coordinates,
        [
            "latitude",
            "longitude",
            "address",
            "place",
            "detail",
            "facility",
            "provider",
            "ssid",
            "manager",
        ],
    ].copy()


@st.cache_resource(show_spinner=False)
def load_geojson(file_path: Path) -> dict:
    """행정경계 GeoJSON을 읽습니다."""
    return json.loads(file_path.read_text(encoding="utf-8"))


@st.cache_resource(show_spinner=False)
def load_pedestrian_light_data(
    file_path: Path,
    file_version: str,
) -> dict:
    """공개 관리시스템에서 받은 비차도 조명 좌표를 읽습니다."""
    # 파일을 같은 이름으로 덮어써도 Streamlit이 예전 캐시를 쓰지 않도록
    # 크기와 수정 시각을 호출 인수에 포함합니다.
    del file_version
    source_payload = json.loads(file_path.read_text(encoding="utf-8"))
    records = []

    for record in source_payload.get("records", []):
        try:
            latitude = float(record["latitude"])
            longitude = float(record["longitude"])
        except (KeyError, TypeError, ValueError):
            continue

        if not (34.8 <= latitude <= 35.6 and 128.1 <= longitude <= 129.0):
            continue

        # 분석과 지도 표시에 필요한 값만 메모리에 유지합니다. 주소·관리번호 등
        # 긴 문자열 27,000여 건은 원본 JSON에 보존하되 앱 메모리에는 복제하지
        # 않습니다.
        records.append(
            [
                latitude,
                longitude,
                str(record.get("district") or "정보 없음"),
            ]
        )

    return {
        "records": records,
        "coverage": source_payload.get("coverage", []),
    }


def distance_in_meters(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    """창원시 범위에서 두 좌표 사이 거리를 미터 단위로 계산합니다."""
    latitude_difference = math.radians(second_latitude - first_latitude)
    longitude_difference = math.radians(
        second_longitude - first_longitude
    )
    average_latitude = math.radians(
        (first_latitude + second_latitude) / 2
    )
    x_distance = longitude_difference * math.cos(average_latitude)
    return 6_371_000 * math.sqrt(
        latitude_difference**2 + x_distance**2
    )


def build_coordinate_buckets(
    coordinates: list[tuple[float, float]],
    cell_size: float = 0.001,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """최근접 시설 검색을 빠르게 하기 위한 간단한 공간 버킷입니다."""
    buckets: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for latitude, longitude in coordinates:
        key = (
            math.floor(latitude / cell_size),
            math.floor(longitude / cell_size),
        )
        buckets.setdefault(key, []).append((latitude, longitude))
    return buckets


def nearest_distance_in_buckets(
    latitude: float,
    longitude: float,
    buckets: dict[tuple[int, int], list[tuple[float, float]]],
    maximum_distance: float,
    cell_size: float = 0.001,
) -> float | None:
    """지정 반경 안에 있는 가장 가까운 시설까지의 거리를 반환합니다."""
    center_key = (
        math.floor(latitude / cell_size),
        math.floor(longitude / cell_size),
    )
    search_range = max(2, math.ceil(maximum_distance / 80))
    nearest_distance: float | None = None

    for latitude_offset in range(-search_range, search_range + 1):
        for longitude_offset in range(-search_range, search_range + 1):
            candidates = buckets.get(
                (
                    center_key[0] + latitude_offset,
                    center_key[1] + longitude_offset,
                ),
                [],
            )
            for candidate_latitude, candidate_longitude in candidates:
                distance = distance_in_meters(
                    latitude,
                    longitude,
                    candidate_latitude,
                    candidate_longitude,
                )
                if distance > maximum_distance:
                    continue
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance

    return nearest_distance


def build_three_factor_support_sites(
    cctv_locations: pd.DataFrame,
    pedestrian_lights: list[list],
    wifi_locations: pd.DataFrame,
    cctv_radius: float = 100,
    light_radius: float = 50,
    grid_size: float = 200,
) -> list[dict]:
    """CCTV·보행조명·Wi-Fi가 모두 가까운 200m 대표 지점을 만듭니다."""
    if cctv_locations.empty or not pedestrian_lights or wifi_locations.empty:
        return []

    cctv_coordinates = [
        (float(row.latitude), float(row.longitude))
        for row in cctv_locations.itertuples(index=False)
    ]
    light_coordinates = [
        (float(record[0]), float(record[1]))
        for record in pedestrian_lights
    ]
    cctv_buckets = build_coordinate_buckets(cctv_coordinates)
    light_buckets = build_coordinate_buckets(light_coordinates)

    candidate_sites = []
    for row in wifi_locations.itertuples(index=False):
        latitude = float(row.latitude)
        longitude = float(row.longitude)
        cctv_distance = nearest_distance_in_buckets(
            latitude,
            longitude,
            cctv_buckets,
            cctv_radius,
        )
        if cctv_distance is None:
            continue

        light_distance = nearest_distance_in_buckets(
            latitude,
            longitude,
            light_buckets,
            light_radius,
        )
        if light_distance is None:
            continue

        candidate_sites.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "cctv_distance": cctv_distance,
                "light_distance": light_distance,
                "wifi_count": int(row.wifi_count),
                "wifi_place": str(row.place),
                "wifi_address": str(row.address),
            }
        )

    reference_latitude = 35.20
    latitude_step = grid_size / 111_320
    longitude_step = grid_size / (
        111_320 * math.cos(math.radians(reference_latitude))
    )
    grouped_sites: dict[tuple[int, int], list[dict]] = {}
    for site in candidate_sites:
        grid_key = (
            math.floor(site["latitude"] / latitude_step),
            math.floor(site["longitude"] / longitude_step),
        )
        grouped_sites.setdefault(grid_key, []).append(site)

    support_sites = []
    for sites in grouped_sites.values():
        representative = min(
            sites,
            key=lambda site: (
                site["cctv_distance"] + site["light_distance"]
            ),
        ).copy()
        representative["support_location_count"] = len(sites)
        representative["wifi_count_in_grid"] = sum(
            site["wifi_count"] for site in sites
        )
        support_sites.append(representative)

    return support_sites


def web_mercator_xy(latitude: float, longitude: float) -> tuple[float, float]:
    """위경도를 생활안전지도 WMS가 사용하는 EPSG:3857 좌표로 바꿉니다."""
    limited_latitude = min(85.05112878, max(-85.05112878, latitude))
    radius = 6_378_137
    x_coordinate = radius * math.radians(longitude)
    y_coordinate = radius * math.log(
        math.tan(math.pi / 4 + math.radians(limited_latitude) / 2)
    )
    return x_coordinate, y_coordinate


@st.cache_data(show_spinner=False)
def boundary_grid_mask(
    boundary_data: dict,
    grid_size: float = ANALYSIS_GRID_SIZE,
) -> dict:
    """창원시 경계 안에 있는 정방형 분석격자를 이미지 마스크로 만듭니다."""
    geometries = [
        feature.get("geometry", {})
        for feature in boundary_data.get("features", [])
    ]
    all_points = []
    polygons = []
    for geometry in geometries:
        coordinates = geometry.get("coordinates", [])
        if geometry.get("type") == "Polygon":
            geometry_polygons = [coordinates]
        elif geometry.get("type") == "MultiPolygon":
            geometry_polygons = coordinates
        else:
            continue
        polygons.extend(geometry_polygons)
        for polygon in geometry_polygons:
            for ring in polygon:
                all_points.extend(ring)

    if not all_points:
        raise ValueError("창원시 경계에서 좌표를 찾지 못했습니다.")

    longitudes = [float(point[0]) for point in all_points]
    latitudes = [float(point[1]) for point in all_points]
    minimum_longitude = min(longitudes)
    maximum_longitude = max(longitudes)
    minimum_latitude = min(latitudes)
    maximum_latitude = max(latitudes)
    reference_latitude = (minimum_latitude + maximum_latitude) / 2
    latitude_step = grid_size / 111_320
    longitude_step = grid_size / (
        111_320 * math.cos(math.radians(reference_latitude))
    )
    row_count = math.ceil(
        (maximum_latitude - minimum_latitude) / latitude_step
    )
    column_count = math.ceil(
        (maximum_longitude - minimum_longitude) / longitude_step
    )

    mask_image = Image.new("L", (column_count, row_count), 0)
    mask_draw = ImageDraw.Draw(mask_image)

    def pixel_point(point: list[float]) -> tuple[float, float]:
        longitude, latitude = float(point[0]), float(point[1])
        return (
            (longitude - minimum_longitude) / longitude_step,
            (maximum_latitude - latitude) / latitude_step,
        )

    for polygon in polygons:
        if not polygon:
            continue
        mask_draw.polygon([pixel_point(point) for point in polygon[0]], fill=1)
        for hole in polygon[1:]:
            mask_draw.polygon([pixel_point(point) for point in hole], fill=0)

    mask = np.asarray(mask_image, dtype=bool)
    row_indexes, column_indexes = np.where(mask)
    center_latitudes = (
        maximum_latitude - (row_indexes + 0.5) * latitude_step
    )
    center_longitudes = (
        minimum_longitude + (column_indexes + 0.5) * longitude_step
    )
    return {
        "mask": mask,
        "rows": row_indexes,
        "columns": column_indexes,
        "latitudes": center_latitudes,
        "longitudes": center_longitudes,
        "bounds": [
            [minimum_latitude, minimum_longitude],
            [maximum_latitude, maximum_longitude],
        ],
        "latitude_step": latitude_step,
        "longitude_step": longitude_step,
    }


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_safemap_risk_image(
    _service_key: str,
    url: str,
    layer: str,
    style: str,
    bounds: tuple[tuple[float, float], tuple[float, float]],
    raster_size: int = RISK_RASTER_SIZE,
) -> bytes:
    """창원시 전체 범죄위험 WMS를 분석용 PNG 한 장으로 요청합니다."""
    (minimum_latitude, minimum_longitude), (
        maximum_latitude,
        maximum_longitude,
    ) = bounds
    minimum_x, minimum_y = web_mercator_xy(
        minimum_latitude, minimum_longitude
    )
    maximum_x, maximum_y = web_mercator_xy(
        maximum_latitude, maximum_longitude
    )
    query = urlencode(
        {
            "serviceKey": _service_key,
            "service": "WMS",
            "request": "GetMap",
            "layers": layer,
            "styles": style,
            "format": "image/png",
            "transparent": "true",
            "version": "1.1.1",
            "width": raster_size,
            "height": raster_size,
            "srs": "EPSG:3857",
            "bbox": f"{minimum_x},{minimum_y},{maximum_x},{maximum_y}",
        }
    )
    separator = "&" if "?" in url else "?"
    with urlopen(f"{url}{separator}{query}", timeout=45) as response:
        content_type = response.headers.get("content-type", "").lower()
        if "image" not in content_type:
            raise ValueError("생활안전지도에서 이미지가 아닌 응답을 받았습니다.")
        return response.read()


def risk_signal_for_grid(
    image_bytes: bytes,
    grid: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """WMS 픽셀 강도를 상대 추정 위험등급 1~5로 변환합니다."""
    image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    pixels = np.asarray(image, dtype=np.float32)
    height, width = pixels.shape[:2]
    (minimum_latitude, minimum_longitude), (
        maximum_latitude,
        maximum_longitude,
    ) = grid["bounds"]
    minimum_x, minimum_y = web_mercator_xy(
        minimum_latitude, minimum_longitude
    )
    maximum_x, maximum_y = web_mercator_xy(
        maximum_latitude, maximum_longitude
    )

    longitudes = grid["longitudes"]
    latitudes = grid["latitudes"]
    x_coordinates = 6_378_137 * np.radians(longitudes)
    limited_latitudes = np.clip(latitudes, -85.05112878, 85.05112878)
    y_coordinates = 6_378_137 * np.log(
        np.tan(np.pi / 4 + np.radians(limited_latitudes) / 2)
    )
    pixel_x = np.clip(
        np.rint(
            (x_coordinates - minimum_x)
            / (maximum_x - minimum_x)
            * (width - 1)
        ),
        0,
        width - 1,
    ).astype(int)
    pixel_y = np.clip(
        np.rint(
            (maximum_y - y_coordinates)
            / (maximum_y - minimum_y)
            * (height - 1)
        ),
        0,
        height - 1,
    ).astype(int)

    rgba = pixels[pixel_y, pixel_x]
    luminance = (
        0.2126 * rgba[:, 0]
        + 0.7152 * rgba[:, 1]
        + 0.0722 * rgba[:, 2]
    ) / 255
    alpha = rgba[:, 3] / 255
    raw_signal = luminance * alpha

    # 이 WMS는 투명한 무자료 대신 일정한 회색 배경을 사용하는 경우가 있다.
    # 창원시 내부에서 가장 자주 나타나는 밝기를 배경으로 간주해 제거하지
    # 않으면 산지와 해안까지 높은 위험등급으로 잘못 분류된다.
    rounded_signal = np.round(raw_signal, 3)
    unique_signal, signal_counts = np.unique(
        rounded_signal,
        return_counts=True,
    )
    background_signal = float(unique_signal[np.argmax(signal_counts)])
    signal = np.maximum(0, raw_signal - background_signal)
    positive = signal > 0.01
    positive_signal = signal[positive]
    if len(positive_signal) < 20:
        raise ValueError("범죄위험 픽셀을 충분히 찾지 못했습니다.")

    # 픽셀 수가 많은 한 가지 색이 여러 분위수 경계를 차지하지 않도록
    # 고유 강도값을 기준으로 상대 위험 단계를 나눈다.
    unique_positive_signal = np.unique(np.round(positive_signal, 4))
    thresholds = np.quantile(
        unique_positive_signal,
        [0.25, 0.5, 0.75],
    )
    grades = np.ones(len(signal), dtype=np.uint8)
    grades[positive] = (
        np.searchsorted(thresholds, signal[positive], side="right") + 2
    )
    return signal, grades


def high_risk_grid_overlay(risk_grades: np.ndarray, grid: dict) -> np.ndarray:
    """원본 WMS 상대 위험도가 높은 격자만 빨간색으로 강조합니다."""
    overlay = np.zeros((*grid["mask"].shape, 4), dtype=np.uint8)
    high_risk = risk_grades >= 4
    highest_risk = risk_grades >= 5
    overlay[grid["rows"][high_risk], grid["columns"][high_risk]] = (
        239,
        68,
        68,
        165,
    )
    overlay[grid["rows"][highest_risk], grid["columns"][highest_risk]] = (
        127,
        29,
        29,
        225,
    )
    return overlay


@st.cache_data(ttl=86_400, show_spinner=False)
def geocode_changwon(place: str) -> dict:
    """창원시 안의 장소명이나 주소를 보행 길찾기 좌표로 변환합니다."""
    query = place.strip()
    if not query:
        raise ValueError("출발지와 도착지를 모두 입력해 주세요.")

    try:
        latitude_text, longitude_text = [
            value.strip() for value in query.split(",", maxsplit=1)
        ]
        latitude = float(latitude_text)
        longitude = float(longitude_text)
        minimum_latitude, minimum_longitude, maximum_latitude, maximum_longitude = (
            CHANGWON_BOUNDS
        )
        if (
            minimum_latitude <= latitude <= maximum_latitude
            and minimum_longitude <= longitude <= maximum_longitude
        ):
            return {
                "latitude": latitude,
                "longitude": longitude,
                "name": query,
            }
    except (ValueError, TypeError):
        pass

    parameters = urlencode(
        {
            "format": "jsonv2",
            "countrycodes": "kr",
            "limit": 1,
            "bounded": 1,
            "viewbox": "128.10,35.55,129.00,34.75",
            "q": f"창원시 {query}",
        }
    )
    try:
        request = Request(
            f"https://nominatim.openstreetmap.org/search?{parameters}",
            headers={"User-Agent": "changwon-night-safety-map/1.0"},
        )
        with urlopen(request, timeout=20) as response:
            results = json.loads(response.read().decode("utf-8"))
        if results:
            return {
                "latitude": float(results[0]["lat"]),
                "longitude": float(results[0]["lon"]),
                "name": str(results[0]["display_name"]).split(
                    ", 대한민국"
                )[0],
            }
    except Exception:
        # Streamlit Cloud의 공용 IP가 Nominatim 호출 제한(HTTP 429)에
        # 걸릴 수 있어 동일 OSM 데이터를 사용하는 Photon으로 재시도한다.
        pass

    photon_parameters = urlencode(
        {
            "q": f"창원시 {query}",
            "limit": 10,
            "lat": 35.23,
            "lon": 128.68,
        }
    )
    photon_request = Request(
        f"https://photon.komoot.io/api/?{photon_parameters}",
        headers={"User-Agent": "changwon-night-safety-map/1.0"},
    )
    try:
        with urlopen(photon_request, timeout=20) as response:
            photon_results = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise ValueError(
            "장소검색 서버가 잠시 혼잡합니다. 잠시 후 다시 시도해 주세요."
        ) from error

    minimum_latitude, minimum_longitude, maximum_latitude, maximum_longitude = (
        CHANGWON_BOUNDS
    )
    candidates = []
    normalized_query = query.replace(" ", "")
    for feature in photon_results.get("features", []):
        properties = feature.get("properties", {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) < 2:
            continue
        longitude, latitude = map(float, coordinates[:2])
        if not (
            minimum_latitude <= latitude <= maximum_latitude
            and minimum_longitude <= longitude <= maximum_longitude
        ):
            continue
        candidate_name = str(properties.get("name") or query)
        candidate_city = str(properties.get("city") or "")
        score = 0
        score += 10 if candidate_name.replace(" ", "") == normalized_query else 0
        score += 5 if "창원" in candidate_city else 0
        score += 2 if properties.get("osm_type") == "W" else 0
        score += 1 if properties.get("housenumber") else 0
        candidates.append((score, feature))

    if not candidates:
        raise ValueError(f"창원시에서 '{query}' 위치를 찾지 못했습니다.")
    _, selected = max(candidates, key=lambda item: item[0])
    properties = selected["properties"]
    longitude, latitude = map(float, selected["geometry"]["coordinates"][:2])
    location_parts = [
        properties.get("name") or query,
        properties.get("street"),
        properties.get("district"),
        properties.get("city"),
    ]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "name": ", ".join(str(part) for part in location_parts if part),
    }


@st.cache_data(ttl=3_600, show_spinner=False)
def fetch_pedestrian_routes(start: dict, destination: dict) -> list[dict]:
    """OpenStreetMap 보행 네트워크에서 최대 3개 대안 경로를 가져옵니다."""
    coordinates = (
        f'{start["longitude"]},{start["latitude"]};'
        f'{destination["longitude"]},{destination["latitude"]}'
    )
    parameters = urlencode(
        {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "alternatives": "3",
        }
    )
    request = Request(
        f"{PEDESTRIAN_ROUTER_URL}/{coordinates}?{parameters}",
        headers={"User-Agent": "changwon-night-safety-map/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise ValueError("보행 가능한 경로를 찾지 못했습니다.")

    return [
        {
            "coordinates": [
                [float(latitude), float(longitude)]
                for longitude, latitude in route["geometry"]["coordinates"]
            ],
            "distance": float(route["distance"]),
            "duration": float(route["duration"]),
        }
        for route in payload["routes"][:3]
    ]


def route_support_count(route: dict, support_sites: list[dict]) -> int:
    """보행경로 120m 안에 있는 안전요소 삼각형 수를 계산합니다."""
    route_points = route["coordinates"]
    return sum(
        1
        for site in support_sites
        if min(
            distance_in_meters(
                site["latitude"],
                site["longitude"],
                point[0],
                point[1],
            )
            for point in route_points
        )
        <= 120
    )


def sampled_route_points(
    coordinates: list[list[float]],
    interval_meters: float = 50,
) -> list[list[float]]:
    """긴 보행로 구간도 빠뜨리지 않도록 일정 간격으로 좌표를 보간합니다."""
    if not coordinates:
        return []
    sampled = [coordinates[0]]
    for start, end in zip(coordinates, coordinates[1:]):
        segment_distance = distance_in_meters(
            start[0], start[1], end[0], end[1]
        )
        step_count = max(1, math.ceil(segment_distance / interval_meters))
        sampled.extend(
            [
                start[0] + (end[0] - start[0]) * step / step_count,
                start[1] + (end[1] - start[1]) * step / step_count,
            ]
            for step in range(1, step_count + 1)
        )
    return sampled


def route_risk_exposure(route: dict, risk_grid: dict | None) -> dict:
    """경로가 원본 범죄위험 고밀도 100m 격자를 지나는 비율을 계산합니다."""
    if not risk_grid:
        return {"count": 0, "highest_count": 0, "percent": None}

    grades = risk_grid["grades"]
    minimum_latitude, minimum_longitude = risk_grid["bounds"][0]
    maximum_latitude, _ = risk_grid["bounds"][1]
    latitude_step = risk_grid["latitude_step"]
    longitude_step = risk_grid["longitude_step"]
    sampled_points = sampled_route_points(route["coordinates"])
    high_risk_count = 0
    highest_risk_count = 0
    valid_count = 0
    for latitude, longitude in sampled_points:
        row = math.floor((maximum_latitude - latitude) / latitude_step)
        column = math.floor((longitude - minimum_longitude) / longitude_step)
        if 0 <= row < grades.shape[0] and 0 <= column < grades.shape[1]:
            grade = int(grades[row, column])
            if grade:
                valid_count += 1
                high_risk_count += int(grade >= 4)
                highest_risk_count += int(grade >= 5)
    return {
        "count": high_risk_count,
        "highest_count": highest_risk_count,
        "percent": (
            high_risk_count / valid_count * 100 if valid_count else None
        ),
    }


def choose_pedestrian_route(
    routes: list[dict],
    support_sites: list[dict],
    night_mode: bool,
    risk_grid: dict | None = None,
) -> dict:
    """밤에는 위험 격자를 피하면서 안전요소가 많은 경로를 선택합니다."""
    shortest_distance = min(route["distance"] for route in routes)
    candidates = [
        route for route in routes if route["distance"] <= shortest_distance * 1.35
    ]
    for route in candidates:
        route["support_count"] = route_support_count(route, support_sites)
        route["risk_exposure"] = route_risk_exposure(route, risk_grid)
    if night_mode and risk_grid:
        return min(
            candidates,
            key=lambda route: (
                route["risk_exposure"]["highest_count"] * 2
                + route["risk_exposure"]["count"],
                -route["support_count"],
                route["distance"],
            ),
        )
    if night_mode and support_sites:
        return max(
            candidates,
            key=lambda route: (route["support_count"], -route["distance"]),
        )
    return min(candidates, key=lambda route: route["distance"])


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


def add_changwon_district_boundary_layer(
    map_object: folium.Map,
    file_path: Path,
) -> bool:
    """창원시 5개 구를 구별되는 색상의 행정경계로 표시합니다."""
    if not file_path.exists():
        return False

    boundary_data = load_geojson(file_path)

    def district_style(feature: dict) -> dict:
        district_name = feature.get("properties", {}).get("name", "")
        color = DISTRICT_COLORS.get(district_name, "#475569")
        return {
            "color": color,
            "weight": 4,
            "opacity": 0.96,
            "fillColor": color,
            "fillOpacity": 0.035,
        }

    def district_highlight(feature: dict) -> dict:
        district_name = feature.get("properties", {}).get("name", "")
        color = DISTRICT_COLORS.get(district_name, "#475569")
        return {
            "color": color,
            "weight": 7,
            "opacity": 1.0,
            "fillOpacity": 0.10,
        }

    folium.GeoJson(
        data=boundary_data,
        name="창원시 5개 구 경계",
        overlay=True,
        control=True,
        show=True,
        style_function=district_style,
        highlight_function=district_highlight,
        tooltip=folium.GeoJsonTooltip(
            fields=["name"],
            aliases=["행정구:"],
            labels=True,
            sticky=False,
        ),
    ).add_to(map_object)
    return True


st.set_page_config(
    page_title="창원시 취약계층 안전 인프라 분석지도",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 100% !important;
        padding-top: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-bottom: 1rem !important;
    }
    [data-testid="stAppViewContainer"] {
        overflow-x: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("창원시 취약계층 안전 인프라 분석지도")
st.write(
    "창원시 취약계층 시설 주변의 범죄위험도와 "
    "안전 인프라 공백을 분석하는 지도입니다."
)
st.caption("행정경계 데이터: © OpenStreetMap contributors (참고용)")
safemap_service_key = get_safemap_service_key()
if not safemap_service_key:
    st.info(
        "범죄주의구간 WMS 레이어를 사용하려면 Streamlit Secrets에 "
        "`SAFEMAP_SERVICE_KEY`를 등록해 주세요."
    )

selected_risk_profile = st.selectbox(
    "안전 대상",
    options=list(SAFEMAP_RISK_PROFILES),
    index=0,
    help="노인·어린이 중 확인할 범죄위험 WMS를 선택합니다.",
)
risk_profile = SAFEMAP_RISK_PROFILES[selected_risk_profile]
st.caption(
    f"현재 범죄위험 레이어: {risk_profile['title']} "
    "(생활안전지도·경찰청 제공)"
)
st.caption(
    "기본 화면에는 원본 범죄위험의 빨간 밀도와 "
    "고위험 격자, 안전요소 3종 충족지점이 표시됩니다."
)

raw_facility_layers = st.multiselect(
    "원본 시설 표시 (필요한 것만 선택)",
    options=["CCTV", "보행조명", "공공 와이파이"],
    default=[],
    help=(
        "선택한 원본 좌표만 지도에 전달합니다. 보행조명 27,000여 건을 "
        "항상 전달하지 않아 Streamlit Community Cloud의 메모리를 절약합니다."
    ),
)

map_object = folium.Map(
    location=[35.1800, 128.6200],
    zoom_start=10,
    min_zoom=9,
    min_lat=34.75,
    max_lat=35.55,
    min_lon=128.10,
    max_lon=129.00,
    max_bounds=True,
    tiles="OpenStreetMap",
    control_scale=True,
    prefer_canvas=True,
)
show_changwon_facilities = True

if safemap_service_key:
    encoded_safemap_key = quote(
        unquote(safemap_service_key),
        safe="",
    )
    folium.raster_layers.WmsTileLayer(
        url=f"{risk_profile['url']}?serviceKey={encoded_safemap_key}",
        layers=risk_profile["layer"],
        styles=risk_profile["style"],
        fmt="image/png",
        transparent=True,
        version="1.1.1",
        attr="생활안전지도·경찰청 (공공누리 제4유형)",
        name=risk_profile["title"],
        overlay=True,
        control=True,
        show=True,
        opacity=0.92,
    ).add_to(map_object)

add_boundary_layer(
    map_object=map_object,
    file_path=CHANGWON_BOUNDARY_FILE,
    layer_name="창원시 외곽경계",
    line_color="#312E81",
)
add_changwon_district_boundary_layer(
    map_object=map_object,
    file_path=CHANGWON_DISTRICTS_BOUNDARY_FILE,
)

map_object.get_root().html.add_child(
    folium.Element(
        """
        <svg aria-hidden="true" width="0" height="0"
             style="position:absolute;width:0;height:0;overflow:hidden">
            <defs>
                <filter id="risk-red-emphasis"
                        x="-40%" y="-40%" width="180%" height="180%"
                        color-interpolation-filters="sRGB">
                    <feColorMatrix in="SourceGraphic"
                                   type="luminanceToAlpha"
                                   result="risk-luminance"></feColorMatrix>
                    <feComponentTransfer in="risk-luminance"
                                         result="risk-mask">
                        <feFuncA type="table"
                                 tableValues="0 0 0 0 0.08 0.28 0.55 0.78 0.92 1 1">
                        </feFuncA>
                    </feComponentTransfer>
                    <feMorphology in="risk-mask" operator="dilate"
                                  radius="1.3" result="risk-core"></feMorphology>
                    <feGaussianBlur in="risk-core" stdDeviation="2.2"
                                    result="risk-glow-mask"></feGaussianBlur>
                    <feFlood flood-color="#FF6B6B" flood-opacity="0.82"
                             result="risk-glow-color"></feFlood>
                    <feComposite in="risk-glow-color" in2="risk-glow-mask"
                                 operator="in" result="risk-glow"></feComposite>
                    <feFlood flood-color="#DC2626" flood-opacity="1"
                             result="risk-core-color"></feFlood>
                    <feComposite in="risk-core-color" in2="risk-core"
                                 operator="in" result="risk-red-core"></feComposite>
                    <feMerge>
                        <feMergeNode in="risk-glow"></feMergeNode>
                        <feMergeNode in="risk-red-core"></feMergeNode>
                    </feMerge>
                </filter>
            </defs>
        </svg>
        <style>
        .leaflet-layer:has(img.leaflet-tile[src*="safemap.go.kr"]) {
            mix-blend-mode: normal !important;
        }
        img.leaflet-tile[src*="safemap.go.kr"] {
            filter: sepia(1) saturate(18) hue-rotate(305deg)
                    contrast(2.1) brightness(1.08);
            filter: url(#risk-red-emphasis);
            mix-blend-mode: normal !important;
        }
        .cctv-cluster {
            display: flex;
            align-items: center;
            justify-content: center;
            background: #DC2626;
            border: 3px solid #7F1D1D;
            border-radius: 50%;
            color: #FFFFFF;
            font-size: 12px;
            font-weight: 800;
            box-shadow: 0 0 0 3px rgba(254, 202, 202, 0.75);
        }
        .cctv-div-icon {
            background: transparent !important;
            border: 0 !important;
        }
        .cctv-camera-symbol {
            position: relative;
            width: 21px;
            height: 13px;
            border: 2px solid #7F1D1D;
            border-radius: 4px;
            background: #DC2626;
            box-shadow: 0 0 0 2px rgba(254, 202, 202, 0.65);
            transform: rotate(-8deg);
        }
        .cctv-camera-symbol::before {
            content: '';
            position: absolute;
            right: -7px;
            top: 2px;
            width: 0;
            height: 0;
            border-top: 4px solid transparent;
            border-bottom: 4px solid transparent;
            border-left: 7px solid #7F1D1D;
        }
        .cctv-camera-lens {
            position: absolute;
            right: 3px;
            top: 3px;
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #FEE2E2;
        }
        .cctv-camera-arm {
            position: absolute;
            left: 4px;
            bottom: -7px;
            width: 10px;
            height: 3px;
            border-radius: 2px;
            background: #7F1D1D;
            transform: rotate(28deg);
        }
        .wifi-cluster {
            display: flex;
            align-items: center;
            justify-content: center;
            background: #7DD3FC;
            border: 3px solid #0284C7;
            border-radius: 50%;
            color: #0C4A6E;
            font-size: 12px;
            font-weight: 800;
            box-shadow: 0 0 0 3px rgba(186, 230, 253, 0.75);
        }
        .wifi-div-icon {
            background: transparent !important;
            border: 0 !important;
        }
        .wifi-symbol {
            position: relative;
            width: 24px;
            height: 24px;
            border: 2px solid #38BDF8;
            border-radius: 50%;
            background: #E0F2FE;
            box-shadow: 0 0 0 2px rgba(186, 230, 253, 0.65);
        }
        .wifi-wave {
            position: absolute;
            left: 50%;
            border: 2px solid transparent;
            border-top-color: #0369A1;
            border-radius: 50%;
            transform: translateX(-50%);
        }
        .wifi-wave-outer {
            top: 5px;
            width: 18px;
            height: 18px;
        }
        .wifi-wave-middle {
            top: 10px;
            width: 10px;
            height: 10px;
        }
        .wifi-dot {
            position: absolute;
            left: 50%;
            bottom: 3px;
            width: 4px;
            height: 4px;
            border-radius: 50%;
            background: #0369A1;
            transform: translateX(-50%);
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
        .map-color-legend {
            position: absolute;
            right: 10px;
            bottom: 38px;
            z-index: 1000;
            min-width: 142px;
            padding: 10px 12px;
            border: 2px solid rgba(0, 0, 0, 0.22);
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.94);
            color: #111827;
            font: 700 13px/1.4 sans-serif;
            box-shadow: 0 1px 5px rgba(0, 0, 0, 0.24);
        }
        .map-color-legend-title {
            margin-bottom: 6px;
            font-size: 13px;
            font-weight: 800;
        }
        .map-color-legend-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 5px;
            white-space: nowrap;
        }
        .leaflet-image-layer {
            image-rendering: pixelated;
        }
        .map-color-swatch {
            display: inline-block;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            box-sizing: border-box;
        }
        .map-color-swatch-cctv {
            background: #DC2626;
            border: 2px solid #7F1D1D;
        }
        .map-color-swatch-light {
            background: #FACC15;
            border: 2px solid #A16207;
        }
        .map-color-swatch-wifi {
            background: #7DD3FC;
            border: 2px solid #0284C7;
        }
        .risk-density-swatch {
            background: #EF4444;
            border: 2px solid #7F1D1D;
            box-shadow: 0 0 0 3px rgba(254, 202, 202, 0.82),
                        0 0 8px rgba(239, 68, 68, 0.88);
        }
        .safe-support-swatch {
            flex: none;
            overflow: visible;
            filter: drop-shadow(0 1px 1px rgba(20, 83, 45, 0.8));
        }
        .safe-support-div-icon {
            background: transparent !important;
            border: 0 !important;
        }
        .safe-support-triangle {
            width: 30px;
            height: 28px;
            filter: drop-shadow(0 2px 2px rgba(20, 83, 45, 0.65));
        }
        .safe-support-triangle svg {
            display: block;
            overflow: visible;
        }
        .map-color-legend-note {
            max-width: 190px;
            margin-top: 7px;
            color: #4B5563;
            font-size: 11px;
            font-weight: 600;
            white-space: normal;
        }
        .map-district-legend-title {
            margin-top: 8px;
            padding-top: 7px;
            border-top: 1px solid #D1D5DB;
            font-size: 12px;
            font-weight: 800;
        }
        .map-district-legend {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 4px 10px;
            margin-top: 5px;
            font-size: 11px;
            font-weight: 700;
        }
        .map-district-legend-item {
            display: flex;
            align-items: center;
            gap: 5px;
            white-space: nowrap;
        }
        .map-district-line {
            width: 15px;
            height: 0;
            border-top: 4px solid;
            border-radius: 2px;
        }
        </style>
        """
    )
)

if show_changwon_facilities:
    map_object.get_root().html.add_child(
        folium.Element(
            """
            <div class="map-color-legend" aria-label="지도 표시 색상">
                <div class="map-color-legend-title">지도 분석 표시</div>
                <div class="map-color-legend-row">
                    <span class="map-color-swatch risk-density-swatch"></span>
                    <span>원본 범죄위험 · 기본 표시</span>
                </div>
                <div class="map-color-legend-row">
                    <svg class="safe-support-swatch" width="18" height="17"
                         viewBox="0 0 18 17" aria-hidden="true">
                        <polygon points="9,1 17,16 1,16" fill="none"
                                 stroke="#16A34A" stroke-width="2.5"
                                 stroke-linejoin="round"></polygon>
                    </svg>
                    <span>안전요소 3종 충족 · 초록 테두리 △</span>
                </div>
                <div class="map-district-legend-title">창원시 5개 구 경계</div>
                <div class="map-district-legend">
                    <div class="map-district-legend-item">
                        <span class="map-district-line" style="border-color:#2563EB"></span>
                        <span>의창구</span>
                    </div>
                    <div class="map-district-legend-item">
                        <span class="map-district-line" style="border-color:#F59E0B"></span>
                        <span>성산구</span>
                    </div>
                    <div class="map-district-legend-item">
                        <span class="map-district-line" style="border-color:#DC2626"></span>
                        <span>마산합포구</span>
                    </div>
                    <div class="map-district-legend-item">
                        <span class="map-district-line" style="border-color:#16A34A"></span>
                        <span>마산회원구</span>
                    </div>
                    <div class="map-district-legend-item">
                        <span class="map-district-line" style="border-color:#7C3AED"></span>
                        <span>진해구</span>
                    </div>
                </div>
                <div class="map-color-legend-note">
                    원본 시설은 지도 위 선택 메뉴에서 필요한 종류만 불러옵니다.
                </div>
            </div>
            """
        )
    )

pedestrian_light_payload = {"records": []}
if show_changwon_facilities and PEDESTRIAN_LIGHT_FILE.exists():
    try:
        pedestrian_light_file_stat = PEDESTRIAN_LIGHT_FILE.stat()
        pedestrian_light_payload = load_pedestrian_light_data(
            PEDESTRIAN_LIGHT_FILE,
            (
                f"{pedestrian_light_file_stat.st_size}:"
                f"{pedestrian_light_file_stat.st_mtime_ns}"
            ),
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

    if "보행조명" in raw_facility_layers:
        ThresholdLightLayer(
            data=pedestrian_lights,
            name="원본 보행조명(차도 가로등 제외)",
            minimum_cluster_size=10,
            cell_size=55,
            show=True,
        ).add_to(map_object)

wifi_data = pd.DataFrame()
wifi_locations = pd.DataFrame()
if show_changwon_facilities:
    if not WIFI_FILE.exists():
        st.warning("와이파이 파일 `data/wifi_data.csv`가 없습니다.")
    else:
        try:
            wifi_data = load_wifi_data(WIFI_FILE)
        except Exception as error:
            st.error(f"와이파이 데이터를 읽지 못했습니다: {error}")

if not wifi_data.empty:
    wifi_locations = (
        wifi_data.groupby(
            ["latitude", "longitude"],
            as_index=False,
            sort=False,
        )
        .agg(
            wifi_count=("latitude", "size"),
            place=("place", combine_unique_text),
            detail=("detail", combine_unique_text),
            facility=("facility", combine_unique_text),
            ssid=("ssid", combine_unique_text),
            provider=("provider", combine_unique_text),
            address=("address", combine_unique_text),
            manager=("manager", combine_unique_text),
        )
    )
    if "공공 와이파이" in raw_facility_layers:
        wifi_markers = [
            [
                row.latitude,
                row.longitude,
                int(row.wifi_count),
                str(row.place),
                str(row.detail),
                str(row.facility),
                str(row.ssid),
                str(row.provider),
                str(row.address),
                str(row.manager),
            ]
            for row in wifi_locations.itertuples(index=False)
        ]
        ThresholdWifiLayer(
            data=wifi_markers,
            name="원본 공공 와이파이",
            minimum_cluster_size=10,
            cell_size=55,
            show=True,
        ).add_to(map_object)

cctv_data = pd.DataFrame()
cctv_locations = pd.DataFrame()
if not show_changwon_facilities:
    pass
elif not CCTV_FILE.exists():
    st.warning(
        "CCTV 파일이 없습니다. `data/cctv_coordinates.xlsx`를 "
        "프로젝트에 넣어 주세요."
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
        cctv_locations = (
            cctv_data.groupby(
                ["latitude", "longitude"],
                as_index=False,
                sort=False,
            )
            .agg(
                camera_count=("camera_count", "sum"),
                address=("address", combine_unique_text),
                purpose=("purpose", combine_unique_text),
                pixels=("pixels", combine_unique_text),
                direction=("direction", combine_unique_text),
            )
        )
        total_count = int(cctv_locations["camera_count"].sum())
        unique_location_count = len(cctv_locations)

        first_column, second_column, third_column, fourth_column = st.columns(4)
        first_column.metric("CCTV 데이터", f"{total_count:,}대")
        second_column.metric("CCTV 위치", f"{unique_location_count:,}곳")
        third_column.metric("보행조명 데이터", f"{len(pedestrian_lights):,}개")
        fourth_column.metric("Wi-Fi 데이터", f"{len(wifi_data):,}개")

        if "CCTV" in raw_facility_layers:
            coverage_points = cctv_locations[
                ["latitude", "longitude"]
            ].values.tolist()
            VisibleCctvCoverageLayer(
                data=coverage_points,
                name="CCTV 촬영범위 약 100m (확대 시)",
                minimum_zoom=14,
                show=False,
            ).add_to(map_object)

            cctv_markers = [
                [
                    row.latitude,
                    row.longitude,
                    int(row.camera_count),
                    str(row.address),
                    str(row.purpose),
                    str(row.pixels),
                    str(row.direction),
                ]
                for row in cctv_locations.itertuples(index=False)
            ]
            ThresholdCctvLayer(
                data=cctv_markers,
                name="원본 방범용 CCTV",
                minimum_cluster_size=10,
                cell_size=55,
                show=True,
            ).add_to(map_object)

route_risk_grid = None
risk_grid_ready = bool(safemap_service_key) and CHANGWON_BOUNDARY_FILE.exists()
if risk_grid_ready:
    try:
        with st.spinner("원본 범죄위험 고밀도 격자를 만들고 있습니다..."):
            analysis_boundary = load_geojson(CHANGWON_BOUNDARY_FILE)
            analysis_grid = boundary_grid_mask(
                analysis_boundary,
                ANALYSIS_GRID_SIZE,
            )
            risk_image_bytes = fetch_safemap_risk_image(
                safemap_service_key,
                risk_profile["url"],
                risk_profile["layer"],
                risk_profile["style"],
                tuple(tuple(value) for value in analysis_grid["bounds"]),
            )
            _, risk_grades = risk_signal_for_grid(
                risk_image_bytes,
                analysis_grid,
            )
            grade_matrix = np.zeros(
                analysis_grid["mask"].shape,
                dtype=np.uint8,
            )
            grade_matrix[
                analysis_grid["rows"], analysis_grid["columns"]
            ] = risk_grades
            route_risk_grid = {
                "grades": grade_matrix,
                "bounds": analysis_grid["bounds"],
                "latitude_step": analysis_grid["latitude_step"],
                "longitude_step": analysis_grid["longitude_step"],
            }

        folium.raster_layers.ImageOverlay(
            image=high_risk_grid_overlay(risk_grades, analysis_grid),
            bounds=analysis_grid["bounds"],
            name="원본 범죄위험 고밀도 격자",
            opacity=1,
            interactive=False,
            cross_origin=False,
            zindex=10,
            show=True,
        ).add_to(map_object)
    except Exception as error:
        st.warning(
            "원본 범죄위험 고밀도 격자를 생성하지 못했습니다. "
            f"기존 지도는 계속 사용할 수 있습니다. ({error})"
        )

support_sites = build_three_factor_support_sites(
    cctv_locations=cctv_locations,
    pedestrian_lights=pedestrian_lights,
    wifi_locations=wifi_locations,
)
if support_sites:
    support_layer = folium.FeatureGroup(
        name="안전요소 3종 충족 △",
        overlay=True,
        control=True,
        show=True,
    )
    for site in support_sites:
        popup_html = (
            '<div style="width:285px;font-size:14px;line-height:1.55">'
            '<b style="color:#15803D">안전요소 3종 충족 △</b><br>'
            f'CCTV 최근접: {site["cctv_distance"]:.0f}m '
            '(100m 기준)<br>'
            f'보행조명 최근접: {site["light_distance"]:.0f}m '
            '(50m 기준)<br>'
            f'공공 Wi-Fi: {escape(site["wifi_place"])}<br>'
            f'주소: {escape(site["wifi_address"])}<br>'
            f'200m 격자 내 충족지점: '
            f'{site["support_location_count"]}곳<br>'
            '<span style="color:#6B7280;font-size:12px">'
            '시설 접근성을 나타내며 절대적인 안전을 보장하지 않습니다.'
            '</span></div>'
        )
        folium.Marker(
            location=[site["latitude"], site["longitude"]],
            tooltip="안전요소 3종 충족 △",
            popup=folium.Popup(popup_html, max_width=320),
            icon=folium.DivIcon(
                html=(
                    '<div class="safe-support-triangle" '
                    'aria-label="안전요소 3종 충족">'
                    '<svg width="30" height="28" viewBox="0 0 30 28" '
                    'aria-hidden="true">'
                    '<polygon points="15,2 28,26 2,26" fill="none" '
                    'stroke="#FFFFFF" stroke-width="6" '
                    'stroke-linejoin="round"></polygon>'
                    '<polygon points="15,2 28,26 2,26" '
                    'fill="rgba(22, 163, 74, 0.04)" '
                    'stroke="#16A34A" stroke-width="3" '
                    'stroke-linejoin="round"></polygon>'
                    '</svg></div>'
                ),
                class_name="safe-support-div-icon",
                icon_size=(34, 34),
                icon_anchor=(17, 28),
                popup_anchor=(0, -24),
            ),
        ).add_to(support_layer)
    support_layer.add_to(map_object)
    st.caption(
        f"안전요소 3종 충족 200m 격자: {len(support_sites):,}곳 "
        "(CCTV 100m·보행조명 50m·공공 Wi-Fi 기준)"
    )

st.subheader("안전 보행 길찾기")
st.caption(
    "창원시 내 장소명이나 주소를 입력하세요. 가장 짧은 경로에서 "
    "35% 이상 크게 우회하지 않으면서 빨간 위험 격자를 덜 지나고 "
    "안전요소 △가 많은 길을 우선 추천합니다."
)
with st.form("night-walking-route-form"):
    route_columns = st.columns(2)
    with route_columns[0]:
        start_query = st.text_input(
            "출발지",
            placeholder="예: 창원시청",
        )
    with route_columns[1]:
        destination_query = st.text_input(
            "도착지",
            placeholder="예: 창원대학교",
        )
    route_submitted = st.form_submit_button(
        "안전 보행경로 찾기",
        type="primary",
        width="stretch",
    )

if route_submitted:
    try:
        with st.spinner("보행로와 주변 안전요소를 비교하고 있습니다..."):
            route_start = geocode_changwon(start_query)
            route_destination = geocode_changwon(destination_query)
            route_candidates = fetch_pedestrian_routes(
                route_start,
                route_destination,
            )
            calculated_at = datetime.now(ZoneInfo("Asia/Seoul"))
            selected_route = choose_pedestrian_route(
                route_candidates,
                support_sites,
                True,
                route_risk_grid,
            )
            arrival_time = calculated_at + timedelta(
                seconds=selected_route["duration"]
            )
            st.session_state["walking_route"] = {
                "start": route_start,
                "destination": route_destination,
                "route": selected_route,
                "calculated_at": calculated_at.strftime("%H:%M"),
                "arrival_time": arrival_time.strftime("%H:%M"),
                "alternative_count": len(route_candidates),
            }
    except Exception as error:
        st.session_state.pop("walking_route", None)
        st.error(f"보행경로를 만들지 못했습니다. {error}")

walking_route = st.session_state.get("walking_route")
if walking_route:
    selected_route = walking_route["route"]
    if not walking_route.get("calculated_at") or not walking_route.get(
        "arrival_time"
    ):
        # 배포 전 세션에 저장된 경로에는 두 필드가 없을 수 있다.
        # 기존 사용자가 새로고침했을 때 KeyError가 나지 않도록 보완한다.
        route_reference_time = datetime.now(ZoneInfo("Asia/Seoul"))
        walking_route["calculated_at"] = route_reference_time.strftime("%H:%M")
        walking_route["arrival_time"] = (
            route_reference_time
            + timedelta(seconds=selected_route.get("duration", 0))
        ).strftime("%H:%M")
    route_layer_name = "안전 추천 보행경로"
    route_layer = folium.FeatureGroup(
        name=route_layer_name,
        overlay=True,
        control=True,
        show=True,
    )
    folium.PolyLine(
        selected_route["coordinates"],
        color="#2563EB",
        weight=8,
        opacity=0.95,
        tooltip=route_layer_name,
    ).add_to(route_layer)
    folium.CircleMarker(
        location=[
            walking_route["start"]["latitude"],
            walking_route["start"]["longitude"],
        ],
        radius=8,
        color="#FFFFFF",
        weight=3,
        fill=True,
        fill_color="#2563EB",
        fill_opacity=1,
        tooltip=f'출발 · {walking_route["start"]["name"]}',
    ).add_to(route_layer)
    folium.Marker(
        location=[
            walking_route["destination"]["latitude"],
            walking_route["destination"]["longitude"],
        ],
        tooltip=f'도착 · {walking_route["destination"]["name"]}',
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(route_layer)
    route_layer.add_to(map_object)
    map_object.fit_bounds(
        [
            [
                walking_route["start"]["latitude"],
                walking_route["start"]["longitude"],
            ],
            [
                walking_route["destination"]["latitude"],
                walking_route["destination"]["longitude"],
            ],
        ],
        padding=(35, 35),
    )

    route_metrics = st.columns(5)
    route_metrics[0].metric(
        "추천 경로",
        route_layer_name,
    )
    route_metrics[1].metric(
        "거리·예상시간",
        f'{selected_route["distance"] / 1000:.1f}km · '
        f'{max(1, round(selected_route["duration"] / 60))}분',
    )
    route_metrics[2].metric(
        "예상 도착",
        walking_route["arrival_time"],
    )
    route_metrics[3].metric(
        "경로 주변 안전 △",
        f'{selected_route.get("support_count", 0)}곳',
    )
    risk_percent = selected_route.get("risk_exposure", {}).get("percent")
    route_metrics[4].metric(
        "고위험 격자 통과",
        f"{risk_percent:.0f}%" if risk_percent is not None else "분석 대기",
    )
    st.success(
        f'{walking_route["calculated_at"]} 출발 기준 · '
        f'{walking_route["alternative_count"]}개 보행경로를 비교해 '
        "고위험 격자를 덜 지나고 안전요소가 많은 경로를 표시했습니다."
    )
    st.caption(
        "이 경로는 OpenStreetMap 보행로와 현재 시설자료를 이용한 참고용입니다. "
        "실제 보도·횡단보도·공사구간과 현장 안전상황을 반드시 확인하세요."
    )
    if st.button("경로 지우기", width="stretch"):
        st.session_state.pop("walking_route", None)
        st.rerun()

folium.LayerControl(collapsed=False).add_to(map_object)

st_folium(
    map_object,
    width=None,
    height=820,
    key=f"changwon-safe-route-v2-{selected_risk_profile}",
    returned_objects=[],
)
