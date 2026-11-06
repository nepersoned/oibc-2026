import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import export_gfs_partial as export


class PartialGFSExportTests(unittest.TestCase):
    def test_failed_day_remains_missing_without_overwrite(self):
        rows=np.array([[lead,100.,3.,40.,3.] for lead in export.g.LEADS])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); raw=root/"raw"; raw.mkdir()
            np.savez(raw/"20240531.npz",rows=rows)
            ledger=root/"ledger.json"
            ledger.write_text(json.dumps({"start":"2024-05-31","end":"2024-06-01","completed":2,
                                           "total":2,"failed":{"20240601":"missing"}}))
            out=root/"partial.parquet"
            args=["export_gfs_partial.py","--ledger",str(ledger),"--out",str(out)]
            with patch.object(export.g,"RAW",str(raw)), patch.object(export.g,"OUT",str(root/"gfs_hourly.parquet")), patch.object(sys,"argv",args):
                export.main()
                with self.assertRaises(ValueError):
                    export.main()
            frame=pd.read_parquet(out)
            self.assertEqual(len(frame),48)
            self.assertEqual(int(frame.gfs_tcc.isna().sum()),24)
            self.assertTrue((raw/"20240531.npz").exists())

    def test_repaired_failed_day_is_included_only_when_supplied(self):
        rows=np.array([[lead,100.,3.,40.,3.] for lead in export.g.LEADS])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); raw=root/"raw"; raw.mkdir(); repair=root/"repair"; repair.mkdir()
            np.savez(raw/"20240531.npz",rows=rows)
            np.savez(repair/"20240601.npz",rows=rows)
            ledger=root/"ledger.json"
            ledger.write_text(json.dumps({"start":"2024-05-31","end":"2024-06-01","completed":2,
                                           "total":2,"failed":{"20240601":"stale index"}}))
            out=root/"partial.parquet"
            args=["export_gfs_partial.py","--ledger",str(ledger),"--out",str(out),"--repair-dir",str(repair)]
            with patch.object(export.g,"RAW",str(raw)), patch.object(export.g,"OUT",str(root/"gfs_hourly.parquet")), patch.object(sys,"argv",args):
                export.main()
            frame=pd.read_parquet(out)
            self.assertEqual(len(frame),48)
            self.assertEqual(int(frame.gfs_tcc.isna().sum()),0)


if __name__=="__main__":
    unittest.main()
