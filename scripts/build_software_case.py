#!/usr/bin/env python3
"""Build and evaluate a frozen npm dependency-network GBBRPM case.

The deps.dev graph is rooted at one exact package version. deps.dev edges
point from a dependent package to a dependency; this script reverses them so
a disturbance at a dependency propagates toward packages that rely on it.
OSV is queried for the exact package versions and the returned records are
frozen under the case data directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from metrics import jaccard, percentile_priority_set, ranked_items, spearman
from model import evaluate_gbbrpm


DEFAULT_SYSTEM = "npm"
DEFAULT_PACKAGE = "express"
DEFAULT_VERSION = "4.18.2"
DEFAULT_TAU_LEVELS = (0.0, 0.25, 0.50, 0.75, 1.0)

SEVERITY_TO_B = {
    "UNKNOWN": 0.0,
    "NONE": 0.0,
    "LOW": 0.25,
    "MODERATE": 0.50,
    "MEDIUM": 0.50,
    "HIGH": 0.75,
    "CRITICAL": 1.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", default=DEFAULT_SYSTEM)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--dependencies-json",
        type=Path,
        help="Use an existing deps.dev response instead of downloading it.",
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=ROOT / "data" / "software" / "express_4.18.2",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=ROOT / "results" / "software" / "express_4.18.2",
    )
    parser.add_argument(
        "--tau-levels",
        type=float,
        nargs="+",
        default=list(DEFAULT_TAU_LEVELS),
    )
    parser.add_argument(
        "--refresh-osv",
        action="store_true",
        help="Replace an existing frozen OSV snapshot.",
    )
    return parser.parse_args()


def request_json(
    url: str,
    *,
    payload: dict | None = None,
    attempts: int = 3,
    timeout: int = 30,
) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "User-Agent": "gbbrpm-research/1.0",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts:
                raise RuntimeError(f"Request failed after {attempts} attempts: {url}") from exc
            time.sleep(attempt)
    raise AssertionError("unreachable")


def dependency_url(system: str, package: str, version: str) -> str:
    quoted_name = urllib.parse.quote(package, safe="")
    quoted_version = urllib.parse.quote(version, safe="")
    return (
        f"https://api.deps.dev/v3alpha/systems/{system}/packages/"
        f"{quoted_name}/versions/{quoted_version}:dependencies"
    )


def load_dependencies(args: argparse.Namespace) -> tuple[dict, str]:
    if args.dependencies_json:
        with args.dependencies_json.open(encoding="utf-8") as handle:
            return json.load(handle), f"provided file: {args.dependencies_json.name}"

    url = dependency_url(args.system, args.package, args.version)
    return request_json(url), url


def version_key(node: dict) -> tuple[str, str, str]:
    key = node["versionKey"]
    return key["system"].lower(), key["name"], key["version"]


def node_id(node: dict) -> str:
    system, name, version = version_key(node)
    return f"{system}:{name}@{version}"


def validate_dependency_response(data: dict) -> None:
    if data.get("error"):
        raise ValueError(f"deps.dev returned an error: {data['error']}")
    if not data.get("nodes"):
        raise ValueError("deps.dev response contains no nodes")
    if not data.get("edges"):
        raise ValueError("deps.dev response contains no edges")
    if sum(node.get("relation") == "SELF" for node in data["nodes"]) != 1:
        raise ValueError("Expected exactly one SELF node")
    if any(node.get("errors") for node in data["nodes"]):
        raise ValueError("One or more dependency nodes contains resolution errors")

    limit = len(data["nodes"])
    for edge in data["edges"]:
        if not (0 <= int(edge["fromNode"]) < limit):
            raise ValueError("fromNode index is outside the node array")
        if not (0 <= int(edge["toNode"]) < limit):
            raise ValueError("toNode index is outside the node array")


def query_osv(nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    queries = []
    for node in nodes:
        system, name, version = version_key(node)
        ecosystem = "npm" if system == "npm" else system
        queries.append(
            {"version": version, "package": {"name": name, "ecosystem": ecosystem}}
        )

    response = request_json("https://api.osv.dev/v1/querybatch", payload={"queries": queries})
    results = response.get("results", [])
    if len(results) != len(nodes):
        raise ValueError("OSV batch response length does not match the query count")

    advisory_ids = sorted(
        {
            advisory["id"]
            for result in results
            for advisory in result.get("vulns", [])
        }
    )

    def fetch(advisory_id: str) -> dict:
        encoded = urllib.parse.quote(advisory_id, safe="")
        return request_json(f"https://api.osv.dev/v1/vulns/{encoded}")

    with ThreadPoolExecutor(max_workers=4) as executor:
        advisories = list(executor.map(fetch, advisory_ids))
    advisories.sort(key=lambda item: item["id"])
    return results, advisories


def freeze_osv_snapshot(
    nodes: list[dict],
    path: Path,
    *,
    refresh: bool,
) -> dict:
    if path.exists() and not refresh:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    results, advisories = query_osv(nodes)
    snapshot = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "query_endpoint": "https://api.osv.dev/v1/querybatch",
        "record_endpoint_template": "https://api.osv.dev/v1/vulns/{id}",
        "exact_version_results": results,
        "advisories": advisories,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(snapshot, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return snapshot


def advisory_severity(advisory: dict) -> str:
    value = advisory.get("database_specific", {}).get("severity", "UNKNOWN")
    return str(value).upper()


def build_tables(data: dict, osv: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = data["nodes"]
    exact_results = osv["exact_version_results"]
    advisories = {item["id"]: item for item in osv["advisories"]}

    node_rows = []
    for index, (node, result) in enumerate(zip(nodes, exact_results)):
        system, name, version = version_key(node)
        ids = sorted(item["id"] for item in result.get("vulns", []))
        severities = [advisory_severity(advisories[item]) for item in ids]
        scores = [SEVERITY_TO_B.get(severity, 0.0) for severity in severities]
        max_score = max(scores, default=0.0)
        max_severity = "NONE"
        if scores:
            max_severity = severities[scores.index(max_score)]

        node_rows.append(
            {
                "node": node_id(node),
                "deps_dev_index": index,
                "ecosystem": system,
                "package": name,
                "version": version,
                "relation_to_root": node.get("relation", ""),
                "bundled": bool(node.get("bundled", False)),
                "B": max_score,
                "max_severity": max_severity,
                "advisory_count": len(ids),
                "advisory_ids": "|".join(ids),
            }
        )

    edge_rows = []
    for edge in data["edges"]:
        dependent_index = int(edge["fromNode"])
        dependency_index = int(edge["toNode"])
        edge_rows.append(
            {
                "source": node_id(nodes[dependency_index]),
                "target": node_id(nodes[dependent_index]),
                "S": 1.0,
                "tau": 1.0,
                "requirement": edge.get("requirement", ""),
                "deps_dev_dependent_index": dependent_index,
                "deps_dev_dependency_index": dependency_index,
            }
        )

    return pd.DataFrame(node_rows), pd.DataFrame(edge_rows)


def validate_tables(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.DiGraph:
    if nodes["node"].duplicated().any():
        raise ValueError("Software case contains duplicate package-version node IDs")
    if edges[["source", "target"]].duplicated().any():
        raise ValueError("Software case contains duplicate reversed dependency edges")

    graph = nx.from_pandas_edgelist(edges, "source", "target", create_using=nx.DiGraph)
    graph.add_nodes_from(nodes["node"])
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Resolved software dependency graph is not a DAG")
    if nx.number_weakly_connected_components(graph) != 1:
        raise ValueError("Resolved software dependency graph is not weakly connected")
    return graph


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_case(
    args: argparse.Namespace,
    data: dict,
    source: str,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    graph: nx.DiGraph,
) -> None:
    args.case_dir.mkdir(parents=True, exist_ok=True)
    dependencies_path = args.case_dir / "deps_dev_dependencies.json"
    if args.dependencies_json:
        if args.dependencies_json.resolve() != dependencies_path.resolve():
            shutil.copyfile(args.dependencies_json, dependencies_path)
    else:
        with dependencies_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")

    nodes.to_csv(args.case_dir / "nodes.csv", index=False)
    edges.to_csv(args.case_dir / "edges.csv", index=False)

    root = nodes.loc[nodes["relation_to_root"] == "SELF", "node"].iloc[0]
    manifest = {
        "case_id": "software_npm_express_4.18.2",
        "role": "cross-domain feasibility and structural propagation case",
        "root_package_version": root,
        "dependency_source": source,
        "dependency_snapshot_sha256": sha256(dependencies_path),
        "osv_snapshot_sha256": sha256(args.case_dir / "osv_snapshot.json"),
        "node_count": int(len(nodes)),
        "edge_count": int(len(edges)),
        "weak_components": nx.number_weakly_connected_components(graph),
        "dag": nx.is_directed_acyclic_graph(graph),
        "vulnerable_node_count": int((nodes["B"] > 0).sum()),
        "advisory_match_count": int(nodes["advisory_count"].sum()),
        "edge_direction": "dependency_to_dependent (reversed from deps.dev)",
        "B_mapping": "maximum OSV/GHSA categorical severity: LOW=.25, MODERATE=.50, HIGH=.75, CRITICAL=1.00",
        "S_mapping": "1.0 for every resolved dependency relation",
        "tau_protocol": list(map(float, args.tau_levels)),
        "validation_scope": "applicability and structural behavior; OSV is an input source, not an independent outcome reference",
    }
    with (args.case_dir / "manifest.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")


def run_case(
    args: argparse.Namespace,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    graph: nx.DiGraph,
) -> None:
    args.results_dir.mkdir(parents=True, exist_ok=True)
    all_risk_rows = []
    all_contribution_rows = []
    summaries = []
    risks: dict[float, dict[str, float]] = {}
    priorities: dict[float, set[str]] = {}

    for tau in map(float, args.tau_levels):
        if not 0 <= tau <= 1:
            raise ValueError("Every tau level must be in [0,1]")
        configured_edges = edges.copy()
        configured_edges["tau"] = tau
        risk, contributions = evaluate_gbbrpm(nodes[["node", "B"]], configured_edges)
        risks[tau] = risk
        priority, nominal_k, cutoff = percentile_priority_set(risk, 0.20)
        priorities[tau] = priority

        for rank, (node, score) in enumerate(ranked_items(risk), start=1):
            metadata = nodes.loc[nodes["node"] == node].iloc[0]
            all_risk_rows.append(
                {
                    "tau": tau,
                    "rank": rank,
                    "node": node,
                    "package": metadata["package"],
                    "version": metadata["version"],
                    "B": float(metadata["B"]),
                    "R": float(score),
                    "priority_top_20pct": node in priority,
                }
            )

        contributions.insert(0, "configured_tau", tau)
        all_contribution_rows.extend(contributions.to_dict("records"))
        summaries.append(
            {
                "tau": tau,
                "node_count": len(risk),
                "positive_risk_nodes": sum(score > 0 for score in risk.values()),
                "max_risk": max(risk.values()),
                "mean_risk": sum(risk.values()) / len(risk),
                "priority_k_nominal": nominal_k,
                "priority_count_with_ties": len(priority),
                "priority_cutoff": cutoff,
                "top_node": ranked_items(risk)[0][0],
            }
        )

    pd.DataFrame(all_risk_rows).to_csv(args.results_dir / "risk_by_tau.csv", index=False)
    pd.DataFrame(all_contribution_rows).to_csv(
        args.results_dir / "edge_contributions_by_tau.csv", index=False
    )
    pd.DataFrame(summaries).to_csv(args.results_dir / "summary_by_tau.csv", index=False)

    reference_tau = max(risks)
    stability_rows = []
    for tau in sorted(risks):
        stability_rows.append(
            {
                "tau": tau,
                "reference_tau": reference_tau,
                "spearman_vs_reference": spearman(risks[tau], risks[reference_tau]),
                "top_20pct_jaccard_vs_reference": jaccard(
                    priorities[tau], priorities[reference_tau]
                ),
            }
        )
    pd.DataFrame(stability_rows).to_csv(
        args.results_dir / "ranking_stability.csv", index=False
    )

    vulnerable = set(nodes.loc[nodes["B"] > 0, "node"])
    reachable = set(vulnerable)
    for source in vulnerable:
        reachable.update(nx.descendants(graph, source))
    structural_rows = []
    for node in nodes["node"]:
        structural_rows.append(
            {
                "node": node,
                "local_vulnerability": node in vulnerable,
                "structurally_reachable_from_vulnerability": node in reachable,
            }
        )
    pd.DataFrame(structural_rows).to_csv(
        args.results_dir / "structural_reachability.csv", index=False
    )


def main() -> None:
    args = parse_args()
    args.case_dir = args.case_dir.resolve()
    args.results_dir = args.results_dir.resolve()
    if args.dependencies_json:
        args.dependencies_json = args.dependencies_json.resolve()

    data, dependency_source = load_dependencies(args)
    validate_dependency_response(data)
    args.case_dir.mkdir(parents=True, exist_ok=True)
    osv_path = args.case_dir / "osv_snapshot.json"
    osv = freeze_osv_snapshot(data["nodes"], osv_path, refresh=args.refresh_osv)
    nodes, edges = build_tables(data, osv)
    graph = validate_tables(nodes, edges)
    save_case(args, data, dependency_source, nodes, edges, graph)
    run_case(args, nodes, edges, graph)

    print(
        "Software case built: "
        f"{len(nodes)} nodes, {len(edges)} reversed edges, "
        f"{int((nodes['B'] > 0).sum())} vulnerable nodes, "
        f"{int(nodes['advisory_count'].sum())} advisory matches."
    )
    print(f"Data: {args.case_dir}")
    print(f"Results: {args.results_dir}")


if __name__ == "__main__":
    main()
