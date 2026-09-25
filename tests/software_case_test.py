from pathlib import Path
import json
import sys

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model import evaluate_gbbrpm


CASE_DIR = ROOT / "data" / "software" / "express_4.18.2"
RESULTS_DIR = ROOT / "results" / "software" / "express_4.18.2"

nodes = pd.read_csv(CASE_DIR / "nodes.csv")
edges = pd.read_csv(CASE_DIR / "edges.csv")
with (CASE_DIR / "manifest.json").open(encoding="utf-8") as handle:
    manifest = json.load(handle)

assert len(nodes) == 71
assert len(edges) == 128
assert manifest["dag"] is True
assert manifest["vulnerable_node_count"] == 7
assert manifest["advisory_match_count"] == 13
assert int((nodes["B"] > 0).sum()) == 7
assert int(nodes["advisory_count"].sum()) == 13
assert set(edges["S"]) == {1.0}

graph = nx.from_pandas_edgelist(edges, "source", "target", create_using=nx.DiGraph)
graph.add_nodes_from(nodes["node"])
assert nx.is_directed_acyclic_graph(graph)
assert nx.number_weakly_connected_components(graph) == 1

risk, contributions = evaluate_gbbrpm(nodes[["node", "B"]], edges)
assert all(0 <= value <= 1 for value in risk.values())
assert np.isclose(risk["npm:express@4.18.2"], 0.997528076171875, atol=1e-12)
assert risk["npm:express@4.18.2"] > risk["npm:body-parser@1.20.1"]
assert len(contributions) == 128

summary = pd.read_csv(RESULTS_DIR / "summary_by_tau.csv")
assert summary["tau"].tolist() == [0.0, 0.25, 0.50, 0.75, 1.0]
assert set(summary["node_count"]) == {71}
assert set(summary["positive_risk_nodes"]) == {7}

print("Software-domain case checks passed.")
