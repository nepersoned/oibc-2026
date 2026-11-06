import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"/"analysis"))
import partial_gfs_runner as runner


class PartialGFSFeatureTests(unittest.TestCase):
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


if __name__=="__main__":
    unittest.main()
