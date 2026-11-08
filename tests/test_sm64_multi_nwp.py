import pandas as pd

from src.analysis.sm64_multi_nwp import parse_dlwrf_index, successful_index_rows


def test_parse_dlwrf_surface_average_field_range_and_period():
    index = "\n".join([
        "1:0:d=2024060100:PRMSL:mean sea level:18 hour fcst:",
        "2:100:d=2024060100:TCDC:entire atmosphere:12-18 hour ave fcst:",
        "3:250:d=2024060100:DLWRF:surface:12-18 hour ave fcst:",
        "4:400:d=2024060100:RH:2 m above ground:18 hour fcst:",
    ])

    assert parse_dlwrf_index(index) == (
        250, 399, 6, "12-18 hour ave fcst"
    )


def test_ignore_instantaneous_or_different_surface_fields():
    index = "\n".join([
        "1:0:d=2024060100:DLWRF:surface:18 hour fcst:",
        "2:100:d=2024060100:DSWRF:surface:12-18 hour ave fcst:",
    ])

    assert parse_dlwrf_index(index) is None


def test_successful_index_rows_handles_csv_numeric_status_and_boolean_text():
    rows = pd.DataFrame({
        "status": [200, "200", 404, "ERROR:Timeout"],
        "field_present": [True, "true", False, "false"],
    })

    assert successful_index_rows(rows).tolist() == [True, True, False, False]
