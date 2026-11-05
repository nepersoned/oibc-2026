"""Characterize existing behavior; this is not permission to fill gaps."""
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ensemble
import scoring


class MissingBehaviorTests(unittest.TestCase):
    def test_ensemble_zero_fills_missing_site_prediction_but_score_rejects(self):
        ts = pd.Timestamp("2024-06-01 11:00", tz="Asia/Seoul")
        actual = pd.DataFrame({"site_id": ["a", "b"], "ts": [ts, ts], "energy": [5., 7.]})
        pred = pd.DataFrame({"site_id": ["a"], "ts": [ts], "kwh": [5.]})
        comp = pd.Series(["G1", "G1"], index=["a", "b"])
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "synthetic.parquet")
            pred.to_parquet(path)
            result = ensemble.group_sum(path, actual, comp)
            self.assertEqual(result.iloc[0], 5.)
        with self.assertRaises(ValueError):
            scoring.score(pred, comp, actual, pd.Series([1.], index=[ts]))


if __name__ == "__main__":
    unittest.main()
