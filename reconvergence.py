"""Shared-origin reconvergence diagnostic for GBBRPM v1.

The path-pruned reference is a counterfactual diagnostic, not a replacement
model or ground truth. Independent source lineages retain bounded noisy-OR
aggregation. Incoming branches whose ancestry overlaps are grouped, and only
the largest contribution in each overlapping group is retained.
"""

import networkx as nx
import numpy as np
import pandas as pd

from model import derive_susceptibility, evaluate_gbbrpm, load_network


def evaluate_path_pruned_reference(nodes, edges):
    edges = derive_susceptibility(edges)
    graph = nx.DiGraph()
    local = {}
    parameters = {}

    for row in nodes.itertuples(index=False):
        node = str(row.node)
        graph.add_node(node)
        local[node] = float(row.B)

    for row in edges.itertuples(index=False):
        source, target = str(row.source), str(row.target)
        graph.add_edge(source, target)
        parameters[(source, target)] = float(row.S) * float(row.tau)

    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("The path-pruned diagnostic requires a DAG")

    risk = {}
    ancestry = {}

    for target in nx.topological_sort(graph):
        incoming = [
            (
                risk[source] * parameters[(source, target)],
                set(ancestry[source]),
            )
            for source in graph.predecessors(target)
        ]

        groups = []
        for contribution, sources in incoming:
            overlapping = [
                index
                for index, (_, existing_sources) in enumerate(groups)
                if sources & existing_sources
            ]

            if not overlapping:
                groups.append([contribution, set(sources)])
                continue

            retained = max(
                [contribution] + [groups[index][0] for index in overlapping]
            )
            merged_sources = set(sources)
            for index in reversed(overlapping):
                merged_sources.update(groups[index][1])
                groups.pop(index)
            groups.append([retained, merged_sources])

        complement = 1.0 - local[target]
        for contribution, _ in groups:
            complement *= 1.0 - contribution
        risk[target] = float(np.clip(1.0 - complement, 0.0, 1.0))

        target_ancestry = set().union(*(sources for _, sources in incoming))
        if local[target] > 0:
            target_ancestry.add(target)
        ancestry[target] = target_ancestry

    return risk


def reconvergence_diagnostic(network, source="historical", outlet=None):
    nodes, edges = load_network(network, source=source)
    ordinary, _ = evaluate_gbbrpm(nodes, edges)
    pruned = evaluate_path_pruned_reference(nodes, edges)

    node_rows = []
    for node in ordinary:
        node_rows.append(
            {
                "network": network,
                "node": node,
                "gbbrpm_risk": ordinary[node],
                "path_pruned_risk": pruned[node],
                "overlap_inflation": ordinary[node] - pruned[node],
            }
        )

    node_results = pd.DataFrame(node_rows)
    outlet_row = node_results[node_results.node == outlet]
    outlet_oi = float(outlet_row.overlap_inflation.iloc[0]) if outlet else np.nan
    outlet_gbbrpm = float(outlet_row.gbbrpm_risk.iloc[0]) if outlet else np.nan
    outlet_pruned = float(outlet_row.path_pruned_risk.iloc[0]) if outlet else np.nan

    summary = {
        "network": network,
        "maximum_oi": float(node_results.overlap_inflation.max()),
        "mean_oi": float(node_results.overlap_inflation.mean()),
        "outlet_oi": outlet_oi,
        "outlet_gbbrpm": outlet_gbbrpm,
        "outlet_path_pruned": outlet_pruned,
    }
    return node_results, summary
