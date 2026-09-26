from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gbbrpm
from gbbrpm import derive_susceptibility, evaluate_gbbrpm
from model import evaluate_gbbrpm as legacy_evaluate_gbbrpm


assert gbbrpm.__version__ == "0.1.0"
assert set(gbbrpm.__all__) == {"derive_susceptibility", "evaluate_gbbrpm"}

nodes = pd.DataFrame({"node": ["A", "B", "C"], "B": [0.8, 0.0, 0.1]})
edges = pd.DataFrame(
    {
        "source": ["A", "B"],
        "target": ["B", "C"],
        "S": [0.5, 0.5],
    }
)

# Public package inputs may omit tau; the documented neutral default is 1.0.
risk, contributions = evaluate_gbbrpm(nodes, edges)
assert np.isclose(risk["A"], 0.8)
assert np.isclose(risk["B"], 0.4)
assert np.isclose(risk["C"], 0.28)
assert np.allclose(contributions["tau"], 1.0)

derived = derive_susceptibility(
    pd.DataFrame(
        {"source": ["A"], "target": ["B"], "L": [75.0], "C": [100.0]}
    )
)
assert np.isclose(derived.loc[0, "S"], 0.75)

# The legacy repository import must resolve to the exact same engine.
legacy_risk, legacy_contributions = legacy_evaluate_gbbrpm(nodes, edges)
assert legacy_risk == risk
pd.testing.assert_frame_equal(legacy_contributions, contributions)

print("Installable package API checks passed.")
