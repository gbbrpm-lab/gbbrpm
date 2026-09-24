from pathlib import Path
import sys

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metrics import priority_set
from model import evaluate_gbbrpm


def fixture():
    nodes = pd.DataFrame(
        {
            "node": ["A", "B", "C", "D", "E"],
            "B": [0.7, 0.0, 0.0, 0.2, 0.0],
        }
    )
    edges = pd.DataFrame(
        [
            ("A", "B", 100.0, 60.0, 0.8),
            ("A", "C", 100.0, 40.0, 0.8),
            ("B", "D", 100.0, 70.0, 0.9),
            ("C", "D", 100.0, 50.0, 0.9),
            ("D", "E", 100.0, 80.0, 1.0),
        ],
        columns=["source", "target", "C", "L", "tau"],
    )
    return nodes, edges


nodes, edges = fixture()
reference, _ = evaluate_gbbrpm(nodes, edges)

# The generic core accepts an explicit domain-supplied S, while drainage can
# continue deriving the same values from L/C.
explicit_s_edges = edges.drop(columns=["L", "C"]).copy()
explicit_s_edges["S"] = (edges["L"] / edges["C"]).clip(0, 1)
explicit_s_risk, _ = evaluate_gbbrpm(nodes, explicit_s_edges)
for node in reference:
    assert np.isclose(explicit_s_risk[node], reference[node], atol=1e-12)

invalid_s = explicit_s_edges.copy()
invalid_s.loc[0, "S"] = 1.1
try:
    evaluate_gbbrpm(nodes, invalid_s)
    raise AssertionError("out-of-range explicit S was not rejected")
except ValueError as error:
    assert "S" in str(error)

try:
    evaluate_gbbrpm(nodes, edges.drop(columns=["L", "C"]))
    raise AssertionError("missing S and L/C was not rejected")
except ValueError as error:
    assert "either explicit S" in str(error)

# Different valid insertion/topological orders produce the same states.
for seed in range(10):
    shuffled_nodes = nodes.sample(frac=1, random_state=seed).reset_index(drop=True)
    shuffled_edges = edges.sample(frac=1, random_state=seed + 100).reset_index(drop=True)
    actual, _ = evaluate_gbbrpm(shuffled_nodes, shuffled_edges)
    for node in reference:
        assert np.isclose(actual[node], reference[node], atol=1e-12)

# Isomorphic relabeling preserves corresponding results.
mapping = {node: f"renamed_{index}" for index, node in enumerate(nodes.node)}
renamed_nodes = nodes.assign(node=nodes.node.map(mapping))
renamed_edges = edges.assign(
    source=edges.source.map(mapping),
    target=edges.target.map(mapping),
)
renamed_risk, _ = evaluate_gbbrpm(renamed_nodes, renamed_edges)
for original, renamed in mapping.items():
    assert np.isclose(reference[original], renamed_risk[renamed], atol=1e-12)

# All-zero local disturbance remains all zero.
zero_risk, _ = evaluate_gbbrpm(nodes.assign(B=0.0), edges)
assert all(np.isclose(value, 0.0, atol=1e-12) for value in zero_risk.values())

# S=0 and tau=0 each gate the selected edge contribution.
s_zero = edges.copy()
s_zero.loc[0, "L"] = 0.0
_, s_zero_q = evaluate_gbbrpm(nodes, s_zero)
assert np.isclose(s_zero_q.iloc[0].Q, 0.0, atol=1e-12)

tau_zero = edges.copy()
tau_zero.loc[0, "tau"] = 0.0
_, tau_zero_q = evaluate_gbbrpm(nodes, tau_zero)
assert np.isclose(tau_zero_q.iloc[0].Q, 0.0, atol=1e-12)

# Increasing susceptibility or transmission cannot reduce any node state.
higher_s = edges.copy()
higher_s.loc[0, "L"] = min(
    float(higher_s.loc[0, "C"]),
    float(higher_s.loc[0, "L"]) + 20.0,
)
higher_s_risk, _ = evaluate_gbbrpm(nodes, higher_s)
assert all(higher_s_risk[node] + 1e-12 >= reference[node] for node in reference)

higher_tau = edges.copy()
higher_tau.loc[0, "tau"] = min(1.0, float(higher_tau.loc[0, "tau"]) + 0.1)
higher_tau_risk, _ = evaluate_gbbrpm(nodes, higher_tau)
assert all(higher_tau_risk[node] + 1e-12 >= reference[node] for node in reference)

# Cycles and invalid graph records are rejected explicitly.
cyclic_edges = pd.concat(
    [
        edges,
        pd.DataFrame(
            [("E", "A", 100.0, 50.0, 1.0)],
            columns=edges.columns,
        ),
    ],
    ignore_index=True,
)
try:
    evaluate_gbbrpm(nodes, cyclic_edges)
    raise AssertionError("cycle was not rejected")
except ValueError as error:
    assert "DAG" in str(error)

invalid_endpoint = edges.copy()
invalid_endpoint.loc[0, "source"] = "UNKNOWN"
try:
    evaluate_gbbrpm(nodes, invalid_endpoint)
    raise AssertionError("missing endpoint was not rejected")
except ValueError as error:
    assert "missing from node table" in str(error)

duplicate_nodes = pd.concat([nodes, nodes.iloc[[0]]], ignore_index=True)
try:
    evaluate_gbbrpm(duplicate_nodes, edges)
    raise AssertionError("duplicate node was not rejected")
except ValueError as error:
    assert "Duplicate node" in str(error)

duplicate_edges = pd.concat([edges, edges.iloc[[0]]], ignore_index=True)
try:
    evaluate_gbbrpm(nodes, duplicate_edges)
    raise AssertionError("duplicate edge was not rejected")
except ValueError as error:
    assert "Duplicate directed edge" in str(error)

invalid_tau = edges.copy()
invalid_tau.loc[0, "tau"] = 1.1
try:
    evaluate_gbbrpm(nodes, invalid_tau)
    raise AssertionError("out-of-range tau was not rejected")
except ValueError as error:
    assert "tau" in str(error)

# Priority sets are deterministic and expand ties at the cutoff.
ties = {"d": 0.7, "b": 0.9, "a": 0.9, "c": 0.7, "e": 0.1}
assert priority_set(ties, 0.20) == {"a", "b"}
assert priority_set(ties, 0.40) == {"a", "b"}
assert priority_set(ties, 0.60) == {"a", "b", "c", "d"}
assert priority_set(dict(reversed(list(ties.items()))), 0.60) == {
    "a",
    "b",
    "c",
    "d",
}
assert priority_set({"a": 0.0, "b": 0.0}, 0.20) == set()

twenty_nodes = {f"n{index:02d}": 21.0 - index for index in range(1, 21)}
assert len(priority_set(twenty_nodes, 0.10)) == 2
assert len(priority_set(twenty_nodes, 0.20)) == 4
assert len(priority_set(twenty_nodes, 0.25)) == 5

print("Generic property checks passed.")
