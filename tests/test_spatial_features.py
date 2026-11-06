import unittest

import numpy as np

from src.spatial_features import summarize_arrays, validate_grib_metadata


class SpatialFeatureTests(unittest.TestCase):
    def test_distribution_direction_and_temporal_features(self):
        ghi = np.array([[1, 2, 3, 4], [2, 3, 4, 5], [3, 4, 5, 6], [4, 5, 6, 7]], dtype=float)
        tcc = 10.0 - ghi
        out = summarize_arrays(ghi, tcc, {"ghi": ghi - 1, "tcc": tcc + 2})
        self.assertAlmostEqual(out["sp_ghi_range"], 6.0)
        self.assertAlmostEqual(out["sp_ghi_east_west"], 2.0)
        self.assertAlmostEqual(out["sp_ghi_north_south"], -2.0)
        self.assertAlmostEqual(out["sp_ghi_change_mean"], 1.0)
        self.assertAlmostEqual(out["sp_tcc_change_mean"], -2.0)

    def test_shape_and_nan_validation(self):
        out = summarize_arrays(np.array([[1.0, np.nan]]), np.array([[2.0, 3.0]]))
        self.assertEqual(out["sp_ghi_p50"], 1.0)
        with self.assertRaises(ValueError):
            summarize_arrays(np.ones((2, 2)), np.ones((2, 3)))

    def test_metadata_and_temporal_contract(self):
        meta = {"shortName": "sdswrf", "typeOfLevel": "surface", "stepType": "avg",
                "startStep": 12, "endStep": 15}
        validate_grib_metadata(meta, "DSWRF")
        with self.assertRaises(ValueError):
            validate_grib_metadata({**meta, "stepType": "instant"}, "DSWRF")
        with self.assertRaises(ValueError):
            validate_grib_metadata({**meta, "endStep": 12}, "DSWRF")
        out = summarize_arrays(np.ones((2, 2)), np.ones((2, 2)))
        self.assertNotIn("sp_ghi_change_mean", out)


if __name__ == "__main__":
    unittest.main()
