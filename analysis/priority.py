"""Target-specific TOP 10 safety infrastructure priority analysis."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def prepare_target_facilities(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize an uploaded daycare/senior-center coordinate table."""
    latitude_column = "latitude" if "latitude" in dataframe else "위도"
    longitude_column = "longitude" if "longitude" in dataframe else "경도"
    if latitude_column not in dataframe or longitude_column not in dataframe:
        raise ValueError("latitude/longitude 또는 위도/경도 컬럼이 필요합니다.")
    name_candidates = ("name", "시설명", "어린이집명", "경로당명")
    name_column = next(
        (column for column in name_candidates if column in dataframe), None
    )
    result = pd.DataFrame(
        {
            "latitude": pd.to_numeric(dataframe[latitude_column], errors="coerce"),
            "longitude": pd.to_numeric(dataframe[longitude_column], errors="coerce"),
            "name": (
                dataframe[name_column].fillna("이름 없음").astype(str)
                if name_column
                else "이름 없음"
            ),
        }
    ).dropna(subset=["latitude", "longitude"])
    return result[
        result["latitude"].between(34.8, 35.6)
        & result["longitude"].between(128.1, 129.0)
    ].reset_index(drop=True)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    latitude_delta = math.radians(lat2 - lat1)
    longitude_delta = math.radians(lon2 - lon1)
    first_latitude = math.radians(lat1)
    second_latitude = math.radians(lat2)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude)
        * math.cos(second_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _point_in_ring(longitude: float, latitude: float, ring: list) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        crosses = (y1 > latitude) != (y2 > latitude)
        if crosses:
            boundary_x = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < boundary_x:
                inside = not inside
        previous = current
    return inside


def district_for_point(latitude: float, longitude: float, geojson: dict) -> str:
    """Return the containing district name from Polygon/MultiPolygon GeoJSON."""
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [])
        polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates
        for polygon in polygons:
            if polygon and _point_in_ring(longitude, latitude, polygon[0]):
                if any(
                    _point_in_ring(longitude, latitude, hole)
                    for hole in polygon[1:]
                ):
                    continue
                properties = feature.get("properties", {})
                return str(properties.get("name") or properties.get("district") or "")
    return ""


def add_target_influence(
    analysis: pd.DataFrame,
    target_facilities: pd.DataFrame | None,
    target_label: str,
    radius_m: float = 300.0,
) -> pd.DataFrame:
    """Attach actual target-facility influence data; preserve missingness if absent."""
    result = analysis.copy()
    result["target_type"] = target_label
    if target_facilities is None or target_facilities.empty:
        result["target_influence"] = pd.NA
        result["target_count_300m"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        result["nearest_target_distance_m"] = np.nan
        result["nearest_target_name"] = pd.NA
        return result

    targets = target_facilities.to_dict("records")
    bucket_step = 0.003
    buckets: dict[tuple[int, int], list[dict]] = {}
    for target in targets:
        key = (
            math.floor(float(target["latitude"]) / bucket_step),
            math.floor(float(target["longitude"]) / bucket_step),
        )
        buckets.setdefault(key, []).append(target)
    influenced = []
    counts = []
    nearest_distances = []
    nearest_names = []
    for row in result.itertuples(index=False):
        center = (
            math.floor(float(row.latitude) / bucket_step),
            math.floor(float(row.longitude) / bucket_step),
        )
        candidates = [
            target
            for row_delta in range(-2, 3)
            for column_delta in range(-2, 3)
            for target in buckets.get(
                (center[0] + row_delta, center[1] + column_delta), []
            )
        ]
        if not candidates:
            influenced.append(False)
            counts.append(0)
            nearest_distances.append(np.nan)
            nearest_names.append(pd.NA)
            continue
        distances = [
            distance_m(row.latitude, row.longitude, target["latitude"], target["longitude"])
            for target in candidates
        ]
        nearest_index = int(np.argmin(distances))
        nearest_distance = float(distances[nearest_index])
        count = sum(distance <= radius_m for distance in distances)
        influenced.append(count > 0)
        counts.append(count)
        nearest_distances.append(nearest_distance)
        nearest_names.append(
            str(candidates[nearest_index].get("name") or "이름 없음")
        )
    result["target_influence"] = influenced
    result["target_count_300m"] = counts
    result["nearest_target_distance_m"] = nearest_distances
    result["nearest_target_name"] = nearest_names
    return result


def build_priority_top10(
    analysis: pd.DataFrame,
    target_label: str,
    district_geojson: dict | None = None,
    limit: int = 10,
    minimum_separation_m: float = 300.0,
) -> pd.DataFrame:
    """Rank high-red-risk, low-infrastructure cells with transparent rules."""
    required = {
        "risk_area_pct",
        "cctv_present",
        "light_present",
        "wifi_present",
        "police_distance_m",
    }
    missing = required.difference(analysis.columns)
    if missing:
        raise ValueError(f"TOP 10 분석에 필요한 컬럼이 없습니다: {', '.join(sorted(missing))}")

    ranked = analysis.copy()
    present_columns = ["cctv_present", "light_present", "wifi_present"]
    ranked["infra_count"] = ranked[present_columns].astype(int).sum(axis=1)
    ranked["infra_score"] = (1.0 + ranked["infra_count"] * 4.0 / 3.0).round(2)
    ranked["missing_infrastructure"] = ranked.apply(
        lambda row: ", ".join(
            label
            for column, label in zip(
                present_columns, ("CCTV", "보안등", "공공 Wi-Fi")
            )
            if not bool(row[column])
        ) or "없음",
        axis=1,
    )
    ranked["priority_score"] = ranked["risk_area_pct"] * (
        1.0 + (3 - ranked["infra_count"]) / 3.0
    )
    ranked = ranked[ranked["risk_area_pct"] > 0]
    if ranked["target_influence"].notna().any():
        ranked = ranked[ranked["target_influence"] == True]  # noqa: E712
    ranked = ranked.sort_values(
        ["priority_score", "risk_area_pct", "infra_count", "police_distance_m"],
        ascending=[False, False, True, False],
        na_position="last",
    )

    selected = []
    for row in ranked.to_dict("records"):
        if any(
            distance_m(row["latitude"], row["longitude"], item["latitude"], item["longitude"])
            < minimum_separation_m
            for item in selected
        ):
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    result = pd.DataFrame(selected)
    if result.empty:
        return result
    if district_geojson:
        result["district"] = [
            district_for_point(row.latitude, row.longitude, district_geojson)
            for row in result.itertuples(index=False)
        ]
    else:
        result["district"] = ""

    def reason(row: pd.Series) -> str:
        police_text = (
            f"최근접 파출소 {row.police_distance_m:.0f}m"
            if pd.notna(row.police_distance_m)
            else "파출소 거리 자료 없음"
        )
        influence_text = ""
        area_text = "창원시 내"
        if pd.notna(row.get("target_influence")):
            influence_text = f", {target_label} 300m 생활권"
            area_text = f"{target_label} 생활권 내"
        return (
            f"{target_label} 범죄 고위험영역 {row.risk_area_pct:.1f}%, "
            f"안전 인프라 {int(row.infra_count)}/3개 충족, {police_text}{influence_text}로 "
            f"{area_text} 안전 인프라 보강 우선지역"
        )

    result["reason"] = result.apply(reason, axis=1)
    result.insert(0, "rank", range(1, len(result) + 1))
    return result
