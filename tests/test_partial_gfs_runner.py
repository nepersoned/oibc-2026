import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
from pandas.testing import assert_frame_equal

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"/"analysis"))
import partial_gfs_runner as runner


class PartialGFSFeatureTests(unittest.TestCase):
    def test_pipeline_mode_is_not_consumed_as_model(self):
        a,rest=runner.parse_args(["--model","group","--gfs-partial","x.parquet","--mode","val"])
        self.assertEqual(a.model,"group")
        self.assertEqual(rest,["--mode","val"])

    def test_matches_original_feature_loader_when_same_data(self):
        ts=pd.date_range("2024-06-01 11:00",periods=3,freq="h",tz="Asia/Seoul")
        wx=pd.DataFrame({"ts":ts,"pt":[0,0,0],"shortwave_radiation":[1.,2.,3.],"cloud_cover":[4.,5.,6.]})
        raw=pd.DataFrame({"ts":ts,"gfs_ghi":[7.,8.,9.],"gfs_kcs":[.1,.2,.3],"gfs_tcc":[20.,30.,40.]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"src").mkdir();(root/"data_ext").mkdir()
            for name in runner.F.EXT_MODELS:
                wx.to_parquet(root/"data_ext"/f"openmeteo_{name}.parquet")
            raw.to_parquet(root/"data_ext"/"gfs_hourly.parquet")
            with patch.object(runner.F,"__file__",str(root/"src"/"features.py")), patch.object(runner.F,"USE_GFS",False), \
                 patch.object(runner.F,"USE_GEFS",False),patch.object(runner.F,"USE_UM",False),patch.object(runner.F,"USE_2024",False),patch.object(runner.F,"ENS_MODE","all"):
                base=runner.F.load_ext("mean")
                runner.F.USE_GFS=True
                expected=runner.F.load_ext("mean")
                actual=runner.attach_gfs(base,raw)
            assert_frame_equal(actual.sort_index(axis=1),expected.sort_index(axis=1),check_dtype=True)

    def test_missing_noaa_value_stays_missing(self):
        ts=pd.date_range("2024-06-01 11:00",periods=2,freq="h",tz="Asia/Seoul")
        base=pd.DataFrame({"ts":ts,"ext_jma_seamless_ghi":[100.,200.],"ext_ghi_ens":[100.,200.]})
        raw=pd.DataFrame({"ts":ts,"gfs_ghi":[np.nan,50.],"gfs_kcs":[np.nan,.5],"gfs_tcc":[np.nan,40.]})
        out=runner.attach_gfs(base,raw)
        self.assertTrue(pd.isna(out.ext_gfs_ghi.iloc[0]))
        self.assertEqual(out.ext_ghi_ens.iloc[0],100.)

    def test_incomplete_validation_window_is_rejected(self):
        ts=pd.date_range("2024-06-01 01:00",periods=24,freq="h",tz="Asia/Seoul")
        raw=pd.DataFrame({"ts":ts,"gfs_ghi":[1.]*24})
        self.assertEqual(runner.validate_eval_coverage(raw,"2024-06-01","2024-06-02"),1.)
        with self.assertRaisesRegex(ValueError,"coverage"):
            runner.validate_eval_coverage(raw,"2024-06-01","2025-06-01")


if __name__=="__main__":
    unittest.main()
