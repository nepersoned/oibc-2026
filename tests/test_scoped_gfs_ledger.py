import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"/"analysis"))
import scoped_gfs_ledger as scope
import fetch_gfs


class ScopedLedgerTests(unittest.TestCase):
    def test_unprocessed_days_are_not_silent_failures(self):
        rows=np.array([[lead,100.,3.,40.,3.] for lead in fetch_gfs.LEADS])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/"raw";raw.mkdir()
            np.savez(raw/"20240531.npz",rows=rows)
            ledger=root/"ledger.json"
            ledger.write_text(json.dumps({"start":"2024-05-31","end":"2024-06-01","failed":{}}))
            out=root/"scope.json"
            args=["scope","--ledger",str(ledger),"--raw-dir",str(raw),"--start","2024-05-31","--end","2024-06-01","--out",str(out)]
            with patch.object(sys,"argv",args):
                with self.assertRaisesRegex(ValueError,"not yet verified"):
                    scope.main()
            self.assertFalse(out.exists())


if __name__=="__main__":
    unittest.main()
