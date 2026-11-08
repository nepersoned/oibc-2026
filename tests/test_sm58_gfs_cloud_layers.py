from datetime import date
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from sm58_fetch_cloud_layers import FIELDS, hourly_rows, messages


def test_index_parser_selects_instantaneous_layer_fields_only():
    lines = [
        "1:0:d=2024060100:LCDC:low cloud layer:18 hour fcst:",
        "2:100:d=2024060100:LCDC:low cloud layer:12-18 hour ave fcst:",
        "3:200:d=2024060100:MCDC:middle cloud layer:18 hour fcst:",
        "4:300:d=2024060100:HCDC:high cloud layer:18 hour fcst:",
        "5:400:d=2024060100:TCDC:entire atmosphere:18 hour fcst:",
    ]
    found = messages("\n".join(lines), 18)
    assert set(found) == set(FIELDS)
    assert found["gfs_lcdc"] == (0, 99)
    assert "gfs_lcdc" in found and "TCDC" not in found


def test_hourly_interpolation_obeys_right_closed_kst_day():
    leads = range(15, 40, 3)
    values = {lead: {name: float(lead) for name in FIELDS} for lead in leads}
    rows = hourly_rows(date(2024, 5, 31), values)
    frame = pd.DataFrame(rows)
    assert len(frame) == 24
    assert frame.ts.iloc[0] == pd.Timestamp("2024-06-01 01:00", tz="Asia/Seoul")
    assert frame.ts.iloc[-1] == pd.Timestamp("2024-06-02 00:00", tz="Asia/Seoul")
    assert frame.gfs_lcdc.iloc[0] == 16.0
    assert frame.gfs_lcdc.iloc[1] == 17.0
    assert frame.gfs_lcdc.iloc[2] == 18.0
    assert (frame[["gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]].to_numpy() >= 0).all()
