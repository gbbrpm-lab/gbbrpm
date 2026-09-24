from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comparators import compare_to_gbbrpm
from model import evaluate_gbbrpm, load_network
from reconvergence import reconvergence_diagnostic
from scenarios import run_core_scenarios


EXPECTED_RECONVERGENCE = {
    "N3": (0.000000, 0.000000, 0.000000, 0.106814, 0.106814),
    "N4": (0.189280, 0.083148, 0.099372, 0.351372, 0.252000),
    "N5": (0.439353, 0.149633, 0.322637, 0.708640, 0.386003),
}


def close(actual, expected, tolerance=5e-7):
    assert np.isclose(actual, expected, atol=tolerance), (actual, expected)


scenario_count = 0
outlets = {"N1": "F", "N2": "H", "N3": "H", "N4": "G", "N5": "N20"}
for network, outlet in outlets.items():
    nodes, edges = load_network(network, source="historical")
    risk, _ = evaluate_gbbrpm(nodes, edges)
    assert all(0 <= value <= 1 for value in risk.values())
    scenario_count += len(run_core_scenarios(network, nodes, edges, outlet))

assert scenario_count == 161

nodes, edges = load_network("N5", source="historical")
comparison = compare_to_gbbrpm(nodes, edges).set_index("comparator")
close(comparison.loc["local_only", "spearman"], 0.108627)
close(comparison.loc["uniform_S_0.75", "spearman"], 0.696241)
close(comparison.loc["local_only", "top_20pct_jaccard"], 0.142857)
close(comparison.loc["uniform_S_0.25", "top_20pct_jaccard"], 0.142857)
close(comparison.loc["uniform_S_0.50", "top_20pct_jaccard"], 0.000000)
close(comparison.loc["uniform_S_0.75", "top_20pct_jaccard"], 0.333333)

for network, expected in EXPECTED_RECONVERGENCE.items():
    _, summary = reconvergence_diagnostic(
        network, source="historical", outlet=outlets[network]
    )
    actual = (
        summary["maximum_oi"],
        summary["mean_oi"],
        summary["outlet_oi"],
        summary["outlet_gbbrpm"],
        summary["outlet_path_pruned"],
    )
    for actual_value, expected_value in zip(actual, expected):
        close(actual_value, expected_value)

print("Reproducibility checks passed: 161 scenarios and archived key values.")
