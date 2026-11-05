import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from leaderboard_proxy import BASE_SCORE, TEAM_BEST, scenarios


class LeaderboardProxyTests(unittest.TestCase):
    def test_relative_scenario_and_best(self):
        r = scenarios(100, 80)
        self.assertEqual(r["local_reduction"], 20)
        self.assertAlmostEqual(r["local_reduction_fraction"], .2)
        self.assertEqual(r["scenarios"][-1]["scenario_score"], BASE_SCORE + 20)
        self.assertEqual(r["scenarios"][-1]["scenario_minus_actual_best"], BASE_SCORE + 20 - TEAM_BEST)

    def test_degradation_and_invalid(self):
        self.assertLess(scenarios(100, 110)["scenarios"][0]["scenario_score"], BASE_SCORE)
        for value in (0, math.nan, math.inf):
            with self.assertRaises(ValueError):
                scenarios(value, 20)


if __name__ == "__main__":
    unittest.main()
