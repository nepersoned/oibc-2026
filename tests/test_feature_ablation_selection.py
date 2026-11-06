import sys
import unittest

import pandas as pd

sys.path.insert(0, "src")
import pipeline


class FeatureAblationSelectionTest(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "site_id": ["PV001"], "ts": [pd.Timestamp("2024-01-01", tz="Asia/Seoul")],
            "energy": [1.0], "smp": [100.0], "current_group": ["A"],
            "capacity_kw": [5.0], "wa_station": ["WA001"], "wb_station": ["WB001"],
            "base_feature": [1.0], "ablation_feature": [2.0],
        })

    def test_drops_only_explicit_features(self):
        self.assertEqual(pipeline.select_rich_features(self.frame, ["ablation_feature"]), ["base_feature"])

    def test_unknown_feature_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown rich feature"):
            pipeline.select_rich_features(self.frame, ["not_a_feature"])

    def test_cannot_drop_every_model_input(self):
        with self.assertRaisesRegex(ValueError, "cannot remove every"):
            pipeline.select_rich_features(self.frame, ["base_feature", "ablation_feature"])

    def test_site_code_categorical_metadata_follows_selection(self):
        self.frame["site_code"] = [1]
        selected = pipeline.select_rich_features(self.frame, ["site_code"])
        self.assertNotIn("site_code", selected)


if __name__ == "__main__":
    unittest.main()
