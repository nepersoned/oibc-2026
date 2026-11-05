"""Run a matched baseline or direct model with an explicit LightGBM seed."""
import argparse
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["base", "direct"], required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--threads", type=int, default=4)
    a, rest = ap.parse_known_args()
    if a.threads < 1:
        raise ValueError("threads must be positive")
    model.PARAMS.update(random_state=a.seed, n_jobs=a.threads)
    script = Path(__file__).parent / ("baseline_float32_reproduction.py" if a.kind == "base" else "direct_irradiance_model.py")
    sys.argv = [str(script)] + rest
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
