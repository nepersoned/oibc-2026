"""Audit reconstructed fixed-grid Open-Meteo files without contest data."""
import argparse

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = parser.parse_args()
    data = pd.read_parquet(args.file)
    if not {"ts", "pt"}.issubset(data.columns):
        raise ValueError("ts and pt are required")
    if data.ts.dt.tz is None:
        raise ValueError("timezone missing")
    fields = [c for c in data if c not in {"ts", "pt"}]
    print(f"rows={len(data)} start={data.ts.min()} end={data.ts.max()} tz={data.ts.dt.tz}")
    print(f"grid_points={data.pt.nunique()} duplicate_pt_ts={data.duplicated(['pt','ts']).sum()}")
    print(f"fields={','.join(fields)}")
    for year, frame in data.groupby(data.ts.dt.year):
        coverage = {c: round(float(frame[c].notna().mean()), 4) for c in fields}
        print(f"year={year} rows={len(frame)} nonnull_fraction={coverage}")


if __name__ == "__main__":
    main()
