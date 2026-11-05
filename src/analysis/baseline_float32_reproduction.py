"""Reproduce historical baseline input casting without changing pipeline.py.

Run with the same CLI as pipeline.py. This diagnostic is for --fset base only.
The historical 77e28d9 model cast input features to float32 in fit and predict.
"""
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model

original_fit = model.fit
original_predict = model.predict


def fit(d, *args, **kwargs):
    if kwargs.get("feats") is not None:
        raise ValueError("This reproducer only supports base features")
    d[model.FEATS] = d[model.FEATS].astype("float32")
    return original_fit(d, *args, **kwargs)


def predict(m, d):
    d[model.FEATS] = d[model.FEATS].astype("float32")
    return original_predict(m, d)


if "--fset" in sys.argv and sys.argv[sys.argv.index("--fset") + 1] != "base":
    raise ValueError("This reproducer only supports --fset base")
model.fit, model.predict = fit, predict
runpy.run_path(str(Path(__file__).resolve().parents[1] / "pipeline.py"), run_name="__main__")
