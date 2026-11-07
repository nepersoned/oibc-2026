import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from composition import local_search


def test_local_search_respects_movable_mask_and_max_changed():
    x0 = np.array([1, 1, 0, 0], dtype=float)
    cap = np.full(4, 25_000.0)
    residuals = np.array([[10.0, 10.0, -10.0, -10.0]])
    weights = np.ones(1)
    x, _ = local_search(x0, residuals, weights, cap, max_rounds=10,
                        movable_mask=np.array([True, False, False, False]),
                        max_changed=1, min_group_capacity=20_100.0)
    changed = np.flatnonzero(x != x0)
    assert len(changed) <= 1
    assert set(changed) <= {0}
    assert cap @ x >= 20_100.0
    assert cap.sum() - cap @ x >= 20_100.0
