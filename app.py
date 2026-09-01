import json
import math
import os
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote

import folium
import pandas as pd
import streamlit as st
from folium.map import Layer
from jinja2 import Template
from streamlit_folium import st_folium


BASE_DIR = Path(__file__).resolve().parent
CCTV_FILE = BASE_DIR / "data" / "cctv_coordinates.xlsx"
WIFI_FILE = BASE_DIR / "data" / "wifi_data.csv"
CHANGWON_BOUNDARY_FILE = BASE_DIR / "data" / "changwon_boundary.geojson"
GIMHAE_BOUNDARY_FILE = BASE_DIR / "data" / "gimhae_boundary.geojson"
TONGYEONG_BOUNDARY_FILE = BASE_DIR / "data" / "tongyeong_boundary.geojson"
PEDESTRIAN_LIGHT_FILE = BASE_DIR / "data" / "nonroad_lights.json"
SAFEMAP_RISK_PROFILES = {
    "여성 버전": {
        "title": "여성 밤길 치안안전",
        "url": "https://www.safemap.go.kr/openapi2/IF_0080_WMS",
        "layer": "A2SM_CRMNLHSPOT_F1_TOT",
        "style": "",
    },
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
                    title: row[4] + ' ' + row[2]
                });

                marker.on('click', function() {
                    if (!marker.getPopup()) {
                        var popup = document.createElement('div');
                        popup.style.width = '260px';
                        popup.style.fontSize = '14px';
                        popup.style.lineHeight = '1.55';

                        var fields = [
                            [row[4], ''],
                            ['관리번호: ', row[2]],
                            ['주소: ', row[3]],
                            ['제공 구: ', row[5]]
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


@st.cache_data(show_spinner=False)
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
    return dataframe.loc[valid_coordinates].copy()


@st.cache_data(show_spinner=False)
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
    return dataframe.loc[valid_coordinates].copy()


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
    pedestrian_lights: list[dict],
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
        (float(record["latitude"]), float(record["longitude"]))
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


st.set_page_config(
    page_title="창원시 안전지도",
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

st.title("창원시 안전지도")
st.write("창원시 방범용 CCTV 위치를 확인할 수 있습니다.")
st.caption("행정경계 데이터: © OpenStreetMap contributors (참고용)")
safemap_service_key = get_safemap_service_key()
if not safemap_service_key:
    st.info(
        "범죄주의구간 WMS 레이어를 사용하려면 Streamlit Secrets에 "
        "`SAFEMAP_SERVICE_KEY`를 등록해 주세요."
    )

map_views = {
    "창원시 중심": {"location": [35.1800, 128.6200], "zoom": 10},
    "김해시 중심": {"location": [35.2500, 128.8800], "zoom": 11},
    "통영시 중심": {"location": [34.8500, 128.4300], "zoom": 10},
    "세 도시 비교": {"location": [34.9000, 128.6000], "zoom": 8},
}
map_view_column, risk_profile_column = st.columns(2)
with map_view_column:
    selected_map_view = st.selectbox(
        "지도 중심",
        options=list(map_views),
        index=0,
    )
with risk_profile_column:
    selected_risk_profile = st.selectbox(
        "안전 대상",
        options=list(SAFEMAP_RISK_PROFILES),
        index=0,
        help="여성·노인·어린이 중 확인할 범죄위험 WMS를 선택합니다.",
    )
map_view = map_views[selected_map_view]
risk_profile = SAFEMAP_RISK_PROFILES[selected_risk_profile]
st.caption(
    f"현재 범죄위험 레이어: {risk_profile['title']} "
    "(생활안전지도·경찰청 제공)"
)
st.caption(
    "기본 화면에는 범죄위험 밀도와 안전요소 3종 충족지점만 표시됩니다. "
    "CCTV·보행조명·Wi-Fi 원본은 지도 우측 목록에서 켤 수 있습니다."
)

map_object = folium.Map(
    location=map_view["location"],
    zoom_start=map_view["zoom"],
    min_zoom=8,
    min_lat=34.45,
    max_lat=36.00,
    min_lon=127.35,
    max_lon=129.50,
    max_bounds=True,
    tiles="OpenStreetMap",
    control_scale=True,
    prefer_canvas=True,
)
show_changwon_facilities = selected_map_view == "창원시 중심"

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
        opacity=0.96,
    ).add_to(map_object)

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
        .leaflet-layer:has(img.leaflet-tile[src*="safemap.go.kr"]) {
            mix-blend-mode: screen !important;
        }
        img.leaflet-tile[src*="safemap.go.kr"] {
            mix-blend-mode: screen !important;
            filter: contrast(2.2) brightness(1.15);
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
            background: #FFFFFF;
            border: 2px solid #111827;
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.9),
                        0 0 9px 4px rgba(255, 255, 255, 0.95);
        }
        .safe-support-swatch {
            width: 0;
            height: 0;
            border-left: 8px solid transparent;
            border-right: 8px solid transparent;
            border-bottom: 15px solid #16A34A;
            filter: drop-shadow(0 1px 1px rgba(20, 83, 45, 0.8));
        }
        .safe-support-div-icon {
            background: transparent !important;
            border: 0 !important;
        }
        .safe-support-triangle {
            color: #16A34A;
            font: 900 32px/30px sans-serif;
            text-align: center;
            text-shadow:
                -2px -2px 0 #FFFFFF,
                 2px -2px 0 #FFFFFF,
                -2px  2px 0 #FFFFFF,
                 2px  2px 0 #FFFFFF,
                 0  3px 5px rgba(20, 83, 45, 0.75);
        }
        .map-color-legend-note {
            max-width: 190px;
            margin-top: 7px;
            color: #4B5563;
            font-size: 11px;
            font-weight: 600;
            white-space: normal;
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
                <div class="map-color-legend-title">기본 분석 표시</div>
                <div class="map-color-legend-row">
                    <span class="map-color-swatch risk-density-swatch"></span>
                    <span>범죄위험 밀도 · 흰색</span>
                </div>
                <div class="map-color-legend-row">
                    <span class="safe-support-swatch"></span>
                    <span>안전요소 3종 충족 · 초록 △</span>
                </div>
                <div class="map-color-legend-note">
                    원본 시설 아이콘은 우측 레이어 목록에서 켤 수 있습니다.
                </div>
            </div>
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

    ThresholdLightLayer(
        data=streetlight_markers,
        name="원본 보행조명(차도 가로등 제외)",
        minimum_cluster_size=10,
        cell_size=55,
        show=False,
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
        show=False,
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

        coverage_points = cctv_locations[
            ["latitude", "longitude"]
        ].values.tolist()
        VisibleCctvCoverageLayer(
            data=coverage_points,
            name="원본 CCTV 촬영범위 약 100m (확대 시)",
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
            show=False,
        ).add_to(map_object)

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
                html='<div class="safe-support-triangle">▲</div>',
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

folium.LayerControl(collapsed=False).add_to(map_object)

st_folium(
    map_object,
    width=None,
    height=820,
    key=f"changwon-safety-map-{selected_map_view}",
    returned_objects=[],
)
