import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, "src")
import features


class ExternalSourceSelectionTest(unittest.TestCase):
    def test_no_openmeteo_uses_gfs_when_openmeteo_files_exist(self):
        ts = pd.date_range("2024-06-01", periods=3, freq="h", tz=features.TZ)

        def exists(path):
            name = str(path).lower()
            return "gfs_hourly_partial_full.parquet" in name or "openmeteo_" in name

        def read(path):
            name = str(path).lower()
            if "openmeteo_" in name:
                raise AssertionError("Open-Meteo was read in no_openmeteo mode")
            return pd.DataFrame({"ts": ts, "gfs_ghi": [100, 200, 300], "gfs_kcs": [1, 1, 1], "gfs_tcc": [0, 0, 0]})

        with patch.object(features, "EXT_SOURCES", "no_openmeteo"), patch.object(features.os.path, "exists", side_effect=exists), patch.object(features.pd, "read_parquet", side_effect=read):
            out = features.load_ext("mean")
        self.assertIn("ext_gfs_ghi", out.columns)
        self.assertIn("ext_ghi_ens", out.columns)
        self.assertFalse(any(c.startswith("ext_jma") or c.startswith("ext_ecmwf") for c in out.columns))
        self.assertTrue(np.isfinite(out["ext_ghi_ens"].dropna()).all())

    def test_no_sources_is_explicit_error(self):
        with patch.object(features, "EXT_SOURCES", "no_openmeteo"), patch.object(features.os.path, "exists", return_value=False):
            with self.assertRaises(FileNotFoundError):
                features.load_ext("mean")


if __name__ == "__main__":
    unittest.main()
