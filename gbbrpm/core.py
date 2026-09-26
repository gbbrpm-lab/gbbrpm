"""Domain-agnostic GBBRPM calculation engine.

The public functions operate on pandas DataFrames and intentionally contain no
repository-specific file paths. Applications can therefore supply synthetic,
operational, or imported networks through the same interface.
"""

import networkx as nx
import pandas as pd


def derive_susceptibility(edges):
    """Return an edge table with a bounded susceptibility column ``S``.

    Drainage-style inputs may provide primitive ``L`` and ``C`` columns, while
    other domains may provide an explicit normalized ``S`` column.
    """

    e = edges.copy()

    if {"L", "C"}.issubset(e.columns):
        if (e.C <= 0).any():
            raise ValueError("C must be > 0")

        if (e.L < 0).any():
            raise ValueError("L must be >= 0")

        e["u"] = e.L / e.C
        e["S"] = e.u.clip(0, 1)
        return e

    if "S" in e.columns:
        susceptibility = pd.to_numeric(e["S"], errors="coerce")
        if susceptibility.isna().any() or (
            (susceptibility < 0) | (susceptibility > 1)
        ).any():
            raise ValueError("S must be numeric and in [0,1]")

        e["S"] = susceptibility.astype(float)
        if "L" not in e.columns:
            e["L"] = float("nan")
        if "C" not in e.columns:
            e["C"] = float("nan")
        if "u" not in e.columns:
            e["u"] = float("nan")
        return e

    raise ValueError("Edges require either explicit S or both C and L")


def evaluate_gbbrpm(nodes, edges):
    """Evaluate one directed acyclic network and return node and edge risks.

    ``nodes`` requires unique ``node`` identifiers and local disturbance ``B``.
    ``edges`` requires ``source`` and ``target`` plus either explicit ``S`` or
    primitive ``L`` and ``C``. ``tau`` is optional and defaults to ``1.0``.
    """

    required_node_columns = {"node", "B"}
    required_edge_columns = {"source", "target"}
    if not required_node_columns.issubset(nodes.columns):
        missing = sorted(required_node_columns - set(nodes.columns))
        raise ValueError(f"Missing node columns: {missing}")
    if not required_edge_columns.issubset(edges.columns):
        missing = sorted(required_edge_columns - set(edges.columns))
        raise ValueError(f"Missing edge columns: {missing}")
    if "S" not in edges.columns and not {"C", "L"}.issubset(edges.columns):
        raise ValueError("Edges require either explicit S or both C and L")

    node_ids = nodes["node"].astype(str)
    if node_ids.duplicated().any():
        duplicates = sorted(node_ids[node_ids.duplicated(keep=False)].unique())
        raise ValueError(f"Duplicate node identifiers: {duplicates}")

    node_set = set(node_ids)
    edge_endpoints = set(edges["source"].astype(str)) | set(
        edges["target"].astype(str)
    )
    missing_endpoints = sorted(edge_endpoints - node_set)
    if missing_endpoints:
        raise ValueError(f"Edge endpoints missing from node table: {missing_endpoints}")

    edge_pairs = edges[["source", "target"]].astype(str)
    if edge_pairs.duplicated().any():
        duplicates = edge_pairs[edge_pairs.duplicated(keep=False)].drop_duplicates()
        duplicate_text = [f"{row.source}->{row.target}" for row in duplicates.itertuples()]
        raise ValueError(f"Duplicate directed edges: {duplicate_text}")

    e = derive_susceptibility(edges)
    if "tau" not in e.columns:
        e["tau"] = 1.0

    tau = pd.to_numeric(e["tau"], errors="coerce")
    if tau.isna().any() or ((tau < 0) | (tau > 1)).any():
        raise ValueError("tau must be numeric and in [0,1]")
    e["tau"] = tau.astype(float)

    graph = nx.DiGraph()
    local_disturbance = {}

    for row in nodes.itertuples(index=False):
        blockage = float(row.B)
        if not 0 <= blockage <= 1:
            raise ValueError("B must be in [0,1]")

        node = str(row.node)
        graph.add_node(node)
        local_disturbance[node] = blockage

    lookup = {}
    for row in e.itertuples(index=False):
        source, target = str(row.source), str(row.target)
        graph.add_edge(source, target)
        lookup[(source, target)] = {
            "S": float(row.S),
            "tau": float(row.tau),
            "L": float(row.L),
            "C": float(row.C),
            "u": float(row.u),
        }

    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("GBBRPM v1 requires a DAG")

    risk = {}
    contributions = []
    for target in nx.topological_sort(graph):
        complement_product = 1.0
        for source in graph.predecessors(target):
            edge = lookup[(source, target)]
            contribution = max(
                0.0,
                min(1.0, edge["S"] * edge["tau"] * risk[source]),
            )
            complement_product *= 1 - contribution
            contributions.append(
                {
                    "source": source,
                    "target": target,
                    "R_source": risk[source],
                    "S": edge["S"],
                    "tau": edge["tau"],
                    "Q": contribution,
                    "L": edge["L"],
                    "C": edge["C"],
                    "u": edge["u"],
                }
            )

        risk[target] = max(
            0.0,
            min(1.0, 1 - (1 - local_disturbance[target]) * complement_product),
        )

    return risk, pd.DataFrame(contributions)
