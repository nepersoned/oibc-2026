import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
import direct_irradiance_model as direct


class DirectWeatherTests(unittest.TestCase):
    def test_spatial_average_and_duplicate_rejection(self):
        ts = pd.Timestamp("2024-06-01 12:00", tz="Asia/Seoul")
        d = pd.DataFrame({"ts": [ts, ts], "pt": [0, 1], "shortwave_radiation": [100., 300.],
                          "cloud_cover": [20., 40.]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wx.parquet"
            d.to_parquet(path)
            out = direct.load_weather(path)
            self.assertEqual(out.ext_ghi.iloc[0], 200.)
            self.assertEqual(out.ext_cloud.iloc[0], 30.)
            pd.concat([d, d.iloc[:1]]).to_parquet(path)
            with self.assertRaises(ValueError):
                direct.load_weather(path)


if __name__ == "__main__":
    unittest.main()
