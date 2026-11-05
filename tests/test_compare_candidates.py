import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "validation"))
from compare_candidates import compare, fit_alpha, validate


class CandidateComparisonTests(unittest.TestCase):
    def test_fit_is_forward_and_exact(self):
        d = pd.DataFrame({"group": ["G1", "G2"], "ts": ["2023-01-01 11:00+09:00"] * 2,
                          "actual": [10., 10.], "smp": [100., 100.], "team": [0., 0.], "candidate": [20., 20.]})
        self.assertAlmostEqual(fit_alpha(validate(d)), .5)
        future = d.copy()
        future["ts"] = "2024-01-01 11:00+09:00"
        result = compare(d, future)
        self.assertEqual(result["models"]["fit_earlier"]["W"], 0.)
        with self.assertRaises(ValueError):
            compare(future, d)

    def test_missing_rejected(self):
        d = pd.DataFrame({"group": ["G1"], "ts": ["2023-01-01 11:00+09:00"], "actual": [1.],
                          "smp": [100.], "team": [None], "candidate": [2.]})
        with self.assertRaises((TypeError, ValueError)):
            validate(d)


if __name__ == "__main__":
    unittest.main()
