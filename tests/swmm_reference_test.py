from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.compare_swmm_reference import compare


detail, summary = compare(data_source="historical")
assert len(detail) == 12
assert int(summary.loc[0, "scenarios"]) == 12
assert np.isclose(
    summary.loc[0, "mean_depth_outside_scope_share"],
    0.712029,
    atol=5e-7,
)
assert np.isclose(
    summary.loc[0, "mean_flooding_outside_scope_share"],
    0.405256,
    atol=5e-7,
)
print("SWMM comparison test passed for 12 blockage scenarios.")
