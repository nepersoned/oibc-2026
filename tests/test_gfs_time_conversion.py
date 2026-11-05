"""Verify GFS math on synthetic arrays; this does not test GRIB decoding."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import fetch_gfs


class GFSTimeConversionTests(unittest.TestCase):
    def test_deaverage_six_hour_window(self):
        rows = np.array([[15, 100., 3, 40., 3], [18, 120., 6, 50., 6]])
        result = fetch_gfs.deaverage(rows)
        self.assertEqual(result[18], (140., 60.))

    def test_build_hourly_synthetic_day(self):
        rows = np.array([[lead, 100., 3, 40., 3] for lead in fetch_gfs.LEADS])
        with tempfile.TemporaryDirectory() as root:
            np.savez(Path(root) / "20240531.npz", rows=rows)
            old = fetch_gfs.RAW
            try:
                fetch_gfs.RAW = root
                frame = fetch_gfs.build_hourly()
            finally:
                fetch_gfs.RAW = old
        self.assertEqual(len(frame), 24)
        self.assertFalse(frame.ts.duplicated().any())
        self.assertEqual(str(frame.ts.dt.tz), "Asia/Seoul")
        self.assertTrue({"ts", "gfs_ghi", "gfs_kcs", "gfs_tcc"}.issubset(frame.columns))


if __name__ == "__main__":
    unittest.main()
