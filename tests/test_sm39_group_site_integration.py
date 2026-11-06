import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
import sm39_group_site_integration as sm39


def example():
    ts = pd.DatetimeIndex([pd.Timestamp("2024-06-01 01:00", tz="Asia/Seoul")])
    sites = pd.DataFrame({"site_id": [1, 2], "capacity_kw": [10.0, 20.0]})
    comp = pd.Series({1: "G1", 2: "G2"})
    site = pd.DataFrame({"site_id": [1, 2], "ts": [ts[0], ts[0]], "kwh": [5.0, 0.0]})
    group = pd.DataFrame({"group": ["G1", "G2"], "ts": [ts[0], ts[0]],
                          "cf_hat": [0.5, 0.25], "pred": [5.0, 5.0]})
    return ts, sites, comp, site, group


class TestSM39(unittest.TestCase):
    def test_redistribution_conserves_group_forecast_and_uses_capacity_when_base_zero(self):
        ts, sites, comp, site, group = example()
        got = sm39.redistribute(site, group, sites, comp, 1.0, ts)
        total = got.assign(group=got.site_id.map(comp)).groupby("group").kwh.sum()
        self.assertEqual(total.to_dict(), {"G1": 5.0, "G2": 5.0})
        self.assertEqual(got.loc[got.site_id == 2, "kwh"].iloc[0], 5.0)

    def test_redistribution_rejects_duplicate_site_keys(self):
        ts, sites, comp, site, group = example()
        bad = pd.concat([site, site.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            sm39.redistribute(bad, group, sites, comp, 0.5, ts)

    def test_bootstrap_is_reproducible_and_168_hour_blocks(self):
        out = sm39.block_bootstrap(np.arange(168 * 3, dtype=float), n_boot=10, seed=7)
        self.assertEqual(out["block_hours"], 168)
        self.assertEqual(out, sm39.block_bootstrap(np.arange(168 * 3, dtype=float), n_boot=10, seed=7))


if __name__ == "__main__":
    unittest.main()
