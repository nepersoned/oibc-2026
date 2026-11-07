"""SM41 preregistered, opt-in cloud attenuation experiment."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import features as F
import pipeline

_original_build = F.build_rich

def build(*args, **kwargs):
    d = _original_build(*args, **kwargs)
    for provider in ("wa", "wb"):
        cloud = d[f"{provider}_cloud"].clip(0, 100).to_numpy() / 100.0
        d[f"sm41_{provider}_cloud_ghi_proxy"] = (d.ghi_cs.to_numpy() * (1 - 0.75 * cloud ** 3.4)).astype("float32")
    return d

if __name__ == "__main__":
    F.build_rich = build
    pipeline.main()
