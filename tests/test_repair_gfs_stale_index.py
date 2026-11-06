import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from repair_gfs_stale_index import metadata_matches


class GFSRepairMetadataTests(unittest.TestCase):
    def test_all_identity_fields_must_match(self):
        meta={"shortName":"sdswrf","typeOfLevel":"surface","paramId":260087,"dataDate":20221130,
              "dataTime":0,"stepType":"avg","startStep":18,"endStep":21}
        self.assertTrue(metadata_matches(meta,"DSWRF",20221130,18,21))
        for field,value in (("dataDate",20221129),("endStep",24),("typeOfLevel","atmosphere"),
                            ("shortName","tcc"),("stepType","instant"),("dataTime",600)):
            bad=dict(meta); bad[field]=value
            self.assertFalse(metadata_matches(bad,"DSWRF",20221130,18,21))


if __name__=="__main__":
    unittest.main()
