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
    result["after_vulnerability"] = np.maximum(
        0.0,
        result["before_vulnerability"] - result["expected_improvement"],
    )
    result = result.sort_values(
        ["expected_improvement", "cost"], ascending=[False, True]
    ).reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))
    return result
