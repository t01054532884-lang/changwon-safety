"""Target-specific TOP 10 safety infrastructure priority analysis.

⚠️ 2026-09-25(Stage 7) 현황 정리 — 이 모듈이 실제로 계산에 쓰이는 범위:
- `prepare_target_facilities()`/`add_target_influence()`: admin/app.py가 지금도 실제로
  호출한다(어린이집/경로당 300m 생활권 판정용). 계속 정상 동작.
- `build_priority_top10()`: **admin/app.py에서 더 이상 호출되지 않는 죽은 코드다.**
  실제 라이브 관리자 웹의 "최종 TOP10"은 Colab 노트북(OOEZ.ipynb STEP0~6)이 산출해 내보낸
  `data/child_top10.csv`/`data/elderly_top10.csv`(+geojson)를 그대로 읽어서 쓴다
  (admin/app.py의 `load_final_top10()` 참고). 이 함수는 노트북이 있기 전에 저장소
  자체적으로 처음 만들었던 독자적인 근사 재구현이고, 지금은 tests/test_vulnerability.py
  테스트로만 유지되고 있다.
- 이 함수의 등급 산정 방식(범죄위험 1~5단계 사분위 이산화 × 인프라부족 1~5단계 이산화를
  곱하는 방식)은 노트북 최종 방법론(CRITIC 연속점수 `vulnerability_score`)과 다르다.
  두 방식을 완전히 동일하게 맞추려면 노트북 STEP2~5의 회귀분석·CRITIC 가중치 도출 과정을
  그대로 재현해야 하는데, 그 중간 산출물(회귀계수, 표본 등)이 이 저장소에 없어 여기서는
  정확히 복제할 수 없다. **다만 이 클러스터링에서 "변만 맞닿은 격자(Rook 인접, 4방향)만
  하나로 묶는다"는 부분은 노트북(Queen 인접, 8방향 — 대각선도 인접으로 취급)과 명백히
  다른 부분이라 아래에서 Queen으로 고쳤다** — 이건 값 재현이 아니라 순수하게 인접 규칙을
  맞추는 문제라 정확히 통일할 수 있었다.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


PRIORITY_MODEL_VERSION = "colab-v3-queen"


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
    """Apply the Colab 1-5 score model and rank contiguous priority clusters."""
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
    if ranked["target_influence"].notna().any():
        ranked = ranked[ranked["target_influence"] == True].copy()  # noqa: E712

    present_columns = ["cctv_present", "light_present", "wifi_present"]
    ranked["infra_count"] = ranked[present_columns].astype(int).sum(axis=1)
    ranked["infra_score"] = (1.0 + ranked["infra_count"] * 4.0 / 3.0).round(2)
    ranked["infra_deficit_count"] = 3 - ranked["infra_count"]
    ranked["infra_deficit_score"] = (6.0 - ranked["infra_score"]).round(2)
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
    # Colab 19단계: 0%는 1점, 양수 격자는 백분위 사분위에 따라 2~5점이다.
    ranked["crime_risk_score"] = 1
    positive = ranked["risk_area_pct"] > 0
    percentiles = ranked.loc[positive, "risk_area_pct"].rank(
        method="average", pct=True
    )
    ranked.loc[positive, "crime_risk_score"] = np.select(
        [percentiles <= 0.25, percentiles <= 0.50, percentiles <= 0.75],
        [2, 3, 4],
        default=5,
    )
    ranked["crime_risk_score"] = ranked["crime_risk_score"].astype(int)

    # Colab 20~21단계: 위험과 부족이 동시에 클 때만 점수가 크게 상승한다.
    ranked["priority_score"] = (
        1.0
        + (ranked["crime_risk_score"] - 1.0)
        * (ranked["infra_deficit_score"] - 1.0)
        / 4.0
    ).round(2)
    ranked["priority_grade"] = (
        ranked["priority_score"].round().clip(1, 5).astype(int)
    )

    # Colab 22단계: 4~5등급 중 변을 맞댄 100m 격자를 하나의 구역으로 묶는다.
    candidates = ranked[ranked["priority_grade"] >= 4].copy()
    if candidates.empty:
        empty_defaults = {
            "rank": pd.Series(dtype="int64"),
            "district": pd.Series(dtype="object"),
            "cluster_grid_count": pd.Series(dtype="int64"),
            "max_priority_grade": pd.Series(dtype="int64"),
            "mean_priority_score": pd.Series(dtype="float64"),
            "max_priority_score": pd.Series(dtype="float64"),
            "mean_risk_pct": pd.Series(dtype="float64"),
            "max_risk_pct": pd.Series(dtype="float64"),
            "cluster_grid_ids": pd.Series(dtype="object"),
            "reason": pd.Series(dtype="object"),
        }
        for column, values in empty_defaults.items():
            candidates[column] = values
        return candidates
    if not {"row", "column"}.issubset(candidates.columns):
        raise ValueError("연속 격자 분석에는 row와 column 컬럼이 필요합니다.")

    coordinates = {
        (int(row.row), int(row.column)): index
        for index, row in candidates.iterrows()
    }
    parent = {index: index for index in candidates.index}

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first, second):
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    # Stage 7(2026-09-25): Rook 인접(변만 맞닿은 4방향) → Queen 인접(대각선 포함 8방향)으로
    # 수정 — 노트북(OOEZ.ipynb STEP6)의 최종 TOP10 클러스터링과 인접 규칙을 통일했다.
    # 대각선으로만 맞닿은 두 고위험 격자가 예전에는 서로 다른 구역으로 쪼개졌지만, 이제는
    # 노트북과 동일하게 하나의 연속 구역으로 묶인다.
    for (grid_row, grid_column), index in coordinates.items():
        for row_delta in (-1, 0, 1):
            for column_delta in (-1, 0, 1):
                if row_delta == 0 and column_delta == 0:
                    continue
                neighbor = (grid_row + row_delta, grid_column + column_delta)
                if neighbor in coordinates:
                    union(index, coordinates[neighbor])

    candidates["cluster_key"] = [find(index) for index in candidates.index]
    summaries = candidates.groupby("cluster_key", as_index=False).agg(
        cluster_grid_count=("grid_id", "size"),
        max_priority_grade=("priority_grade", "max"),
        mean_priority_score=("priority_score", "mean"),
        max_priority_score=("priority_score", "max"),
        mean_risk_pct=("risk_area_pct", "mean"),
        max_risk_pct=("risk_area_pct", "max"),
    )
    summaries = summaries.sort_values(
        [
            "max_priority_grade",
            "mean_priority_score",
            "cluster_grid_count",
            "max_risk_pct",
        ],
        ascending=[False, False, False, False],
    ).head(limit)

    # 지도와 표에는 각 구역에서 점수가 가장 높은 대표 격자를 사용한다.
    selected = []
    for summary in summaries.to_dict("records"):
        cluster = candidates[candidates["cluster_key"] == summary["cluster_key"]]
        representative = cluster.sort_values(
            ["priority_grade", "priority_score", "risk_area_pct", "grid_id"],
            ascending=[False, False, False, True],
        ).iloc[0].to_dict()
        representative.update(summary)
        representative["cluster_grid_ids"] = ",".join(sorted(cluster["grid_id"]))
        selected.append(representative)

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
        influence_text = ""
        area_text = "창원시 내"
        if pd.notna(row.get("target_influence")):
            influence_text = f", {target_label} 300m 생활권"
            area_text = f"{target_label} 생활권 내"
        return (
            f"{target_label} 범죄 고위험영역 {row.risk_area_pct:.1f}%, "
            f"안전 인프라 부족 {int(row.infra_deficit_count)}/3개, "
            f"연속 고취약 격자 {int(row.cluster_grid_count)}개{influence_text}로 "
            f"{area_text} 안전 인프라 보강 우선지역"
        )

    result["reason"] = result.apply(reason, axis=1)
    result.insert(0, "rank", range(1, len(result) + 1))
    # 이전 호출부의 인자는 호환성을 위해 남기되 Colab 군집 방식에서는 사용하지 않는다.
    _ = minimum_separation_m
    return result
