import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from compare_site_predictions import compare


class CompareTests(unittest.TestCase):
    def test_missing_prediction_is_not_zero_filled(self):
        ts = pd.Timestamp("2024-06-01 11:00", tz="Asia/Seoul")
        actual = pd.DataFrame({"site_id": ["a", "b"], "ts": [ts, ts], "energy": [5., 7.]})
        base = pd.DataFrame({"site_id": ["a", "b"], "ts": [ts, ts], "kwh": [4., 6.]})
        candidate = base.iloc[:1].copy()
        comp = pd.Series(["G1", "G1"], index=["a", "b"])
        smp = pd.Series([10.], index=[ts])
        weather = pd.DataFrame({"clearness": [0.8]}, index=pd.DatetimeIndex([ts.floor("D")], name="day"))
        with self.assertRaises(ValueError):
            compare(base, candidate, actual, comp, smp, weather)


if __name__ == "__main__":
    unittest.main()
