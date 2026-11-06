import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"/"validation"))
from historical_blend_cv import diagnostic


class HistoricalCVTests(unittest.TestCase):
    def test_weights_are_applied_to_opposite_fold(self):
        d=pd.DataFrame({"group":["G1","G1"],"ts":["2024-07-01 11:00+09:00","2025-01-01 11:00+09:00"],
                        "actual":[10.,16.],"smp":[1.,1.],"team":[0.,0.],"candidate":[20.,20.]})
        result=diagnostic(d,"2024-06-01")
        self.assertAlmostEqual(result["folds"][0]["group_weight"],.5)
        self.assertAlmostEqual(result["folds"][1]["group_weight"],.8)
        self.assertAlmostEqual(result["cv_W"],3.6)


if __name__=="__main__":
    unittest.main()
