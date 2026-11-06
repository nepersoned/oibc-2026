import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"/"validation"))
from build_ens_v2_oof import attach_group


class BuildV2Tests(unittest.TestCase):
    def test_refuses_capacity_mismatch(self):
        t=pd.Timestamp("2024-06-01 11:00",tz="Asia/Seoul")
        table=pd.DataFrame({"group":["G1"],"ts":[t],"actual":[10.],"smp":[5.],"team":[12.],"candidate":[11.]})
        group=pd.DataFrame({"group":["G1"],"ts":[t],"pred":[10.],"cap_avail":[100.]})
        cap=pd.DataFrame({"group":["G1"],"ts":[t],"observed_cap":[100.]})
        self.assertAlmostEqual(attach_group(table,group,cap).team.iloc[0],.472*12+.528*10)
        cap.loc[0,"observed_cap"]=99.
        with self.assertRaises(ValueError):
            attach_group(table,group,cap)


if __name__=="__main__":
    unittest.main()
