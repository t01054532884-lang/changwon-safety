"""Stage 7: citizen-app 백엔드(scoring.py)의 risk_at()이 Colab 노트북 최종
vulnerability_score(data/child_grid_colab.csv, data/elderly_grid_colab.csv)를
실제로 반영하는지 검증한다.

citizen-app/backend는 독립 배포되는 별도 서비스라 이 저장소 루트 tests/와는 다른
sys.path 설정이 필요하므로, 이 파일 안에서 직접 그 경로를 추가한다.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "citizen-app" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd  # noqa: E402

import scoring  # noqa: E402


class GridVulnerabilityTests(unittest.TestCase):
    def test_known_high_vulnerability_grid_cell_is_picked_up_exactly(self):
        """data/child_grid_colab.csv의 실제 최고값 격자(G052911, 0.5486)에서
        정확히 그 값을 돌려주는지 확인한다(감쇠 없이, 거리 60m 이내)."""
        df = pd.read_csv(REPO_ROOT / "data" / "child_grid_colab.csv")
        top_row = df.sort_values("vulnerability_score", ascending=False).iloc[0]
        score = scoring.grid_vulnerability_at(
            float(top_row["latitude"]), float(top_row["longitude"]), "child"
        )
        self.assertAlmostEqual(score, float(top_row["vulnerability_score"]), places=6)

    def test_far_from_any_flagged_grid_cell_returns_zero(self):
        # 창원시 경계 밖 먼 좌표 — 어떤 격자와도 300m 이내일 수 없다.
        score = scoring.grid_vulnerability_at(36.5, 127.5, "child")
        self.assertEqual(score, 0.0)

    def test_adult_mode_checks_both_child_and_elderly_grids(self):
        child_df = pd.read_csv(REPO_ROOT / "data" / "child_grid_colab.csv")
        top_row = child_df.sort_values("vulnerability_score", ascending=False).iloc[0]
        adult_score = scoring.grid_vulnerability_at(
            float(top_row["latitude"]), float(top_row["longitude"]), "adult"
        )
        child_score = scoring.grid_vulnerability_at(
            float(top_row["latitude"]), float(top_row["longitude"]), "child"
        )
        self.assertAlmostEqual(adult_score, child_score, places=6)

    def test_risk_at_is_higher_near_flagged_hotspot_than_far_away(self):
        df = pd.read_csv(REPO_ROOT / "data" / "child_grid_colab.csv")
        top_row = df.sort_values("vulnerability_score", ascending=False).iloc[0]
        hotspot_risk = scoring.risk_at(
            float(top_row["latitude"]), float(top_row["longitude"]), "child"
        )
        # 창원시 경계 밖 임의 좌표는 실측 시설 데이터도, 격자 데이터도 없어 위험도가 낮다.
        far_risk = scoring.risk_at(36.5, 127.5, "child")
        self.assertGreater(hotspot_risk, far_risk)
        self.assertLessEqual(hotspot_risk, 1.0)
        self.assertGreaterEqual(far_risk, 0.0)

    def test_risk_at_stays_within_zero_one_bounds(self):
        df = pd.read_csv(REPO_ROOT / "data" / "child_grid_colab.csv")
        sample = df.sample(20, random_state=42)
        for _, row in sample.iterrows():
            for age_group in ("child", "senior", "adult"):
                r = scoring.risk_at(float(row["latitude"]), float(row["longitude"]), age_group)
                self.assertGreaterEqual(r, 0.0)
                self.assertLessEqual(r, 1.0)


if __name__ == "__main__":
    unittest.main()
