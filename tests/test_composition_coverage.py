import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from composition_coverage import objective, optimize


class CoverageTests(unittest.TestCase):
    def test_freezing_low_coverage_prevents_move(self):
        initial = np.array([1., 1., 0.])
        residual = np.array([[2., 0., -2.]])
        weights = np.array([1.])
        capacity = np.ones(3)
        unrestricted = optimize(initial, residual, weights, capacity, np.ones(3, dtype=bool), min_capacity=1)
        frozen = optimize(initial, residual, weights, capacity, np.array([False, True, True]), min_capacity=1)
        self.assertEqual(unrestricted[0], 0)
        self.assertEqual(frozen[0], 1)
        self.assertLessEqual(objective(unrestricted, residual, weights), objective(initial, residual, weights))


if __name__ == "__main__":
    unittest.main()
