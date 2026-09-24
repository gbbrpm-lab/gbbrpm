from pathlib import Path
import pandas as pd
import networkx as nx

DATA_DIR = Path(__file__).resolve().parent / "data"

HISTORICAL_DIR = DATA_DIR / "historical"
RECOVERED_DIR = DATA_DIR / "recovered_candidate"

HISTORICAL_EDGE_FILE = HISTORICAL_DIR / "validation_reconstructed_edges.csv"
HISTORICAL_NODE_FILE = HISTORICAL_DIR / "validation_reconstructed_nodes.csv"

RECOVERED_EDGE_FILE = RECOVERED_DIR / "N1-N5_edge_dataset.csv"
RECOVERED_NODE_FILE = RECOVERED_DIR / "N1-N5_node_dataset.csv"

RECOVERED_NETWORK_MAP = {
    "N1": "N1_Linear",
    "N2": "N2_Branching",
    "N3": "N3_Converging",
    "N4": "N4_Diamond",
    "N5": "N5_Mixed20",
}


def load_network(network, source="historical"):
    if source == "historical":
        nodes = pd.read_csv(HISTORICAL_NODE_FILE)
        edges = pd.read_csv(HISTORICAL_EDGE_FILE)

        nodes = nodes[nodes["Network"] == network].copy()
        edges = edges[edges["Network"] == network].copy()
        nodes = nodes.rename(
            columns={"Node": "node"}
        )

        edges = edges.rename(
            columns={"src": "source", "dst": "target"}
        )

    elif source == "recovered":
        nodes = pd.read_csv(RECOVERED_NODE_FILE)
        edges = pd.read_csv(RECOVERED_EDGE_FILE)

        if network not in RECOVERED_NETWORK_MAP:
            raise ValueError(f"Unknown network: {network}")

        recovered_name = RECOVERED_NETWORK_MAP[network]

        nodes = nodes[nodes["Network"] == recovered_name].copy()
        edges = edges[edges["Network"] == recovered_name].copy()
        nodes = nodes.rename(
            columns={"Node": "node","Local_Blockage_B": "B"}
        )

        edges = edges.rename(
            columns={
                "From": "source",
                "To": "target",
                "Capacity_C": "C",
                "Load_L": "L",
                "Tau_baseline": "tau",
            }
        )

        if "Utilization_u" in edges.columns:
            expected_u = edges["L"] / edges["C"]
            if not expected_u.round(10).equals(edges["Utilization_u"].round(10)):
                raise ValueError("Stored Utilization_u does not match L/C")

        if "Susceptibility_S" in edges.columns:
            expected_s = (edges["L"] / edges["C"]).clip(0, 1)
            if not expected_s.round(10).equals(edges["Susceptibility_S"].round(10)):
                raise ValueError("Stored Susceptibility_S does not match min(1, L/C)")

    else:
        raise ValueError(f"Unknown data source: {source}. " "Use 'historical' or 'recovered'.")

    if nodes.empty:
        raise ValueError(f"No nodes found for network {network} " f"using source {source}")

    if edges.empty:
        raise ValueError(f"No edges found for network {network} " f"using source {source}")

    if "tau" not in edges.columns:
        edges["tau"] = 1.0

    return nodes, edges


def derive_susceptibility(edges):
    e = edges.copy()

    # Primitive L/C inputs take precedence for backward-compatible drainage
    # runs. Other domains may supply S directly by omitting L and C.
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

    if "tau" in edges.columns:
        tau = pd.to_numeric(edges["tau"], errors="coerce")
        if tau.isna().any() or ((tau < 0) | (tau > 1)).any():
            raise ValueError("tau must be numeric and in [0,1]")

    e = derive_susceptibility(edges)
    G = nx.DiGraph()
    B = {}

    for r in nodes.itertuples(index=False):
        b = float(r.B)
        if not 0 <= b <= 1:
            raise ValueError("B must be in [0,1]")

        node = str(r.node)
        G.add_node(node)
        B[node] = b

    lookup = {}

    for r in e.itertuples(index=False):
        u, v = str(r.source), str(r.target)
        G.add_edge(u, v)
        lookup[(u, v)] = {
            "S": float(r.S),
            "tau": float(r.tau),
            "L": float(r.L),
            "C": float(r.C),
            "u": float(r.u),
        }

    if not nx.is_directed_acyclic_graph(G):
        raise ValueError("GBBRPM v1 requires a DAG")

    risk = {}
    contrib = []

    for j in nx.topological_sort(G):
        prod = 1.0
        for i in G.predecessors(j):
            p = lookup[(i, j)]
            q = max(0.0, min(1.0, p["S"] * p["tau"] * risk[i]))
            prod *= 1 - q
            contrib.append(
                {
                    "source": i,
                    "target": j,
                    "R_source": risk[i],
                    "S": p["S"],
                    "tau": p["tau"],
                    "Q": q,
                    "L": p["L"],
                    "C": p["C"],
                    "u": p["u"],
                }
            )

        risk[j] = max(0.0, min(1.0, 1 - (1 - B[j]) * prod))

    return risk, pd.DataFrame(contrib)
