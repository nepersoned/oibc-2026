import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from settlement_decomposition import decompose


class TestDecomposition(unittest.TestCase):
    def test_oracles_and_bound(self):
        t = pd.date_range("2024-06-01 11:00", periods=2, freq="h", tz="Asia/Seoul")
        f = pd.DataFrame({"group": ["G1", "G1", "G2", "G2"], "ts": list(t) * 2,
                          "act": [1., 3., 3., 1.], "pred": [2., 2., 2., 2.], "smp": [10.] * 4})
        r = decompose(f)
        self.assertAlmostEqual(r["W_all"], 12.)
        self.assertAlmostEqual(r["W_total_oracle"], 12.)
        self.assertAlmostEqual(r["W_shape_oracle"], 0.)
        self.assertAlmostEqual(r["W_lower_bound"], 0.)
        self.assertEqual(r["W_11_15"], r["W_all"])

    def test_zero_day_and_midnight(self):
        f = pd.DataFrame({"group": ["G1", "G1"], "ts": pd.to_datetime(["2024-06-01 23:00+09:00", "2024-06-02 00:00+09:00"]),
                          "act": [0., 0.], "pred": [1., 1.], "smp": [1., 1.]})
        r = decompose(f)
        self.assertEqual(r["excluded_group_days"], 1)
        self.assertEqual(r["W_common"], 0.)

    def test_missing_rejected(self):
        f = pd.DataFrame({"group": ["G1"], "ts": ["2024-06-01 11:00+09:00"], "act": [1.], "pred": [float("nan")], "smp": [1.]})
        with self.assertRaises(ValueError):
            decompose(f)


if __name__ == "__main__":
    unittest.main()
