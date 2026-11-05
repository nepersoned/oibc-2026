import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import recover_gfs_checked as recover


class RecoveryChecks(unittest.TestCase):
    def test_cache_validation_rejects_missing(self):
        rows=np.array([[lead, 100., 3., 40., 3.] for lead in recover.g.LEADS])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"synthetic.npz"
            np.savez(path,rows=rows)
            recover.inspect_rows(path)
            rows[2,1]=np.nan
            np.savez(path,rows=rows)
            with self.assertRaises(ValueError):
                recover.inspect_rows(path)


if __name__ == "__main__":
    unittest.main()
