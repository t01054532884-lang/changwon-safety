"""Budget-constrained infrastructure placement using 0-1 knapsack DP."""

from __future__ import annotations

import numpy as np
import pandas as pd


FACILITY_EFFECTS = {
    "CCTV": {"key": "cctv", "weight": 0.40, "target_score": 85.0},
    "보안등": {"key": "light", "weight": 0.35, "target_score": 85.0},
    "공공 와이파이": {"key": "wifi", "weight": 0.10, "target_score": 75.0},
}


def build_candidates(
    analysis: pd.DataFrame,
    costs: dict[str, int],
    cells_per_facility: int = 50,
) -> pd.DataFrame:
    """Create evidence-based candidates from high-vulnerability infrastructure gaps."""
    candidates = []
    for facility, settings in FACILITY_EFFECTS.items():
        score_column = f"{settings['key']}_accessibility_score"
        if score_column not in analysis:
            continue
        ranked = analysis.assign(
            _effect=(
                np.maximum(0.0, settings["target_score"] - analysis[score_column])
                * settings["weight"]
                * (0.5 + analysis["vulnerability_score"] / 100.0)
            )
        ).nlargest(cells_per_facility, "_effect")
        for row in ranked.to_dict("records"):
            effect = float(row["_effect"])
            if effect <= 0 or int(costs[facility]) <= 0:
                continue
            candidates.append(
                {
                    "candidate_id": f"{row['grid_id']}:{settings['key']}",
                    "grid_id": row["grid_id"],
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "facility": facility,
                    "cost": int(costs[facility]),
                    "expected_improvement": effect,
                    "before_vulnerability": float(row["vulnerability_score"]),
                    "reason": (
                        f"취약도 {row['vulnerability_score']:.1f}점, "
                        f"{facility} 접근성 {row[score_column]:.1f}점"
                    ),
                }
            )
    return pd.DataFrame(candidates)


def optimize_budget(
    candidates: pd.DataFrame,
    budget: int,
    unit_won: int = 100_000,
) -> pd.DataFrame:
    """Solve the generated 0-1 knapsack exactly on rounded-up cost units."""
    if candidates.empty or budget <= 0:
        return candidates.iloc[0:0].copy()
    capacity = budget // unit_won
    if capacity <= 0:
        return candidates.iloc[0:0].copy()
    weights = np.ceil(candidates["cost"].to_numpy() / unit_won).astype(int)
    values = candidates["expected_improvement"].to_numpy(dtype=float)
    dp = np.full(capacity + 1, -np.inf)
    dp[0] = 0.0
    take = np.zeros((len(candidates), capacity + 1), dtype=bool)
    for item_index, (weight, value) in enumerate(zip(weights, values)):
        if weight > capacity:
            continue
        previous = dp.copy()
        proposed = previous[:-weight] + value
        improved = proposed > dp[weight:]
        dp[weight:][improved] = proposed[improved]
        take[item_index, weight:][improved] = True

    remaining = int(np.nanargmax(dp))
    selected_indexes = []
    for item_index in range(len(candidates) - 1, -1, -1):
        if take[item_index, remaining]:
            selected_indexes.append(item_index)
            remaining -= weights[item_index]
    result = candidates.iloc[list(reversed(selected_indexes))].copy()
    if result.empty:
        return result
    # 같은 격자에 여러 시설이 선정되면 감소량을 합산한다.
    total_improvement = result.groupby("grid_id")["expected_improvement"].transform("sum")
    result["after_vulnerability"] = np.maximum(
        0.0,
        result["before_vulnerability"] - total_improvement,
    )
    result = result.sort_values(
        ["expected_improvement", "cost"], ascending=[False, True]
    ).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    return result


# ---------------------------------------------------------------------------
# Colab 최종 분석(STEP 4~5)과 동일한 산식 기반 후보 생성
#   취약점수 = (범죄 고위험 적색영역 비율 / 100) × CRITIC 인프라 부족점수
#   시설 f 설치 시 감소량 = 위험점수 × CRITIC 가중치_f  (산식이 선형이라 정확히 일치)
# ---------------------------------------------------------------------------
CRITIC_WEIGHTS = {
    "어린이": {"CCTV": 0.3459, "보안등": 0.4499, "공공 와이파이": 0.2043},
    "노인": {"CCTV": 0.3292, "보안등": 0.4928, "공공 와이파이": 0.1780},
}
NEED_COLUMNS = {
    "CCTV": "need_cctv",
    "보안등": "need_light",
    "공공 와이파이": "need_wifi",
}


def build_candidates_colab(
    grid: pd.DataFrame,
    costs: dict[str, int],
    target_label: str,
    max_cells: int = 500,
) -> pd.DataFrame:
    """Colab 생활권 격자(취약점수 > 0)에서 부족한 시설별 설치 대안을 만든다."""
    weights = CRITIC_WEIGHTS[target_label]
    base = grid[grid["vulnerability_score"] > 0].nlargest(
        max_cells, "vulnerability_score"
    )
    candidates = []
    for row in base.to_dict("records"):
        for facility, need_column in NEED_COLUMNS.items():
            if int(row[need_column]) != 1 or int(costs.get(facility, 0)) <= 0:
                continue
            improvement = float(row["risk_score"]) * weights[facility]
            candidates.append(
                {
                    "candidate_id": f"{row['grid_id']}:{need_column}",
                    "grid_id": row["grid_id"],
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "facility": facility,
                    "cost": int(costs[facility]),
                    "expected_improvement": improvement,
                    "before_vulnerability": float(row["vulnerability_score"]),
                    "reason": (
                        f"고위험영역 {row['risk_pct']:.1f}%, {facility} 없음 "
                        f"(CRITIC 가중치 {weights[facility]:.3f})"
                    ),
                }
            )
    return pd.DataFrame(candidates)
