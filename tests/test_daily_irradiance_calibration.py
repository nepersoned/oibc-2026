import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
import daily_irradiance_calibration as cal


class CalibrationTests(unittest.TestCase):
    def test_missing_forecast_falls_back_to_one(self):
        n = 40
        train = pd.DataFrame({"group": ["G1"] * n + ["G2"] * n, "valid": [True] * (2*n),
                              "coverage": [0.5] * (2*n), "hours": [24] * (2*n),
                              "ratio": [1.1] * (2*n), "ghi": np.arange(2*n) + 1.})
        test = pd.DataFrame({"group": ["G1", "G2"], "valid": [False, True], "ghi": [np.nan, 10.]})
        f = cal.factors(train, test, "B_ghi")
        self.assertEqual(f[0], 1.)
        self.assertTrue(0.5 <= f[1] <= 1.5)

    def test_weather_requires_eight_well_populated_hours(self):
        ts = pd.date_range("2024-06-01 09:00", periods=8, freq="h", tz="Asia/Seoul")
        data = pd.DataFrame([{"ts": t, "pt": p, "shortwave_radiation": 200., "cloud_cover": 30.}
                             for t in ts for p in range(25)])
        data.loc[(data.ts == ts[0]) & (data.pt >= 19), "shortwave_radiation"] = np.nan
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weather.parquet"
            data.to_parquet(path)
            self.assertFalse(bool(cal.build_weather(path).iloc[0].valid))


if __name__ == "__main__":
    unittest.main()
