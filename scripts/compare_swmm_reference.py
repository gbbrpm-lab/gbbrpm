"""Compare GBBRPM changes with the stored SWMM external-reference results.

This script defines an explicit, reproducible comparison protocol. It does
not claim numerical equivalence between the GBBRPM risk index and hydraulic
depth or flooding volume.
"""

from pathlib import Path
import sys

import networkx as nx
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from metrics import jaccard, spearman, topk  # noqa: E402
from model import evaluate_gbbrpm, load_network  # noqa: E402

SWMM_DIR = REPO_ROOT / "data" / "swmm"
EXTRACTED_DIR = SWMM_DIR / "extracted"


def positive_change(scenario, baseline, column):
    change = scenario.set_index("Node")[column] - baseline.set_index("Node")[column]
    return change.clip(lower=0.0)


def compare(data_source="historical"):
    manifest = pd.read_csv(SWMM_DIR / "scenario_manifest.csv")
    hydraulics = pd.read_csv(EXTRACTED_DIR / "swmm_hydraulic_results.csv")
    hydraulic_baseline = hydraulics[hydraulics.Scenario == "N5_SWMM_base"]

    nodes, edges = load_network("N5", source=data_source)
    baseline_risk, _ = evaluate_gbbrpm(nodes, edges)
    baseline_risk = pd.Series(baseline_risk, dtype=float)
    graph = nx.from_pandas_edgelist(
        edges,
        source="source",
        target="target",
        create_using=nx.DiGraph,
    )

    rows = []
    for scenario in manifest.itertuples(index=False):
        source, target = scenario.BlockedEdge.split("->")
        scenario_edges = edges.copy()
        blocked = (scenario_edges.source == source) & (
            scenario_edges.target == target
        )
        if int(blocked.sum()) != 1:
            raise ValueError(f"Blocked edge not found exactly once: {scenario.BlockedEdge}")

        # Area loss is represented as a reduction in effective capacity.
        scenario_edges.loc[blocked, "C"] *= 1.0 - float(scenario.AreaLoss)
        scenario_risk, _ = evaluate_gbbrpm(nodes, scenario_edges)
        risk_change = (pd.Series(scenario_risk) - baseline_risk).clip(lower=0.0)

        hydraulic_scenario = hydraulics[hydraulics.Scenario == scenario.Scenario]
        if hydraulic_scenario.empty:
            raise ValueError(f"Missing hydraulic results for {scenario.Scenario}")

        downstream = set(nx.descendants(graph, target)) | {target}
        outside = set(baseline_risk.index) - downstream

        row = {
            "scenario": scenario.Scenario,
            "blocked_edge": scenario.BlockedEdge,
            "area_loss": float(scenario.AreaLoss),
        }

        for label, column in (
            ("depth", "MaxDepth"),
            ("flooding", "FloodVolume"),
        ):
            hydraulic_change = positive_change(
                hydraulic_scenario, hydraulic_baseline, column
            )
            comparison_nodes = set(risk_change[risk_change > 0].index) | set(
                hydraulic_change[hydraulic_change > 0].index
            )
            risk_values = risk_change.reindex(comparison_nodes).fillna(0.0).to_dict()
            hydraulic_values = (
                hydraulic_change.reindex(comparison_nodes).fillna(0.0).to_dict()
            )

            row[f"{label}_spearman"] = spearman(risk_values, hydraulic_values)
            row[f"{label}_top3_jaccard"] = jaccard(
                topk({k: v for k, v in risk_values.items() if v > 0}),
                topk({k: v for k, v in hydraulic_values.items() if v > 0}),
            )
            total_change = float(hydraulic_change.sum())
            row[f"{label}_outside_scope_share"] = (
                float(hydraulic_change.reindex(outside).fillna(0.0).sum())
                / total_change
                if total_change > 0
                else np.nan
            )

        rows.append(row)

    detail = pd.DataFrame(rows)
    summary = pd.DataFrame(
        [
            {
                "scenarios": len(detail),
                "mean_depth_spearman": detail.depth_spearman.mean(),
                "mean_flooding_spearman": detail.flooding_spearman.mean(),
                "mean_depth_top3_jaccard": detail.depth_top3_jaccard.mean(),
                "mean_flooding_top3_jaccard": detail.flooding_top3_jaccard.mean(),
                "mean_depth_outside_scope_share": (
                    detail.depth_outside_scope_share.mean()
                ),
                "mean_flooding_outside_scope_share": (
                    detail.flooding_outside_scope_share.mean()
                ),
            }
        ]
    )
    return detail, summary


if __name__ == "__main__":
    details, summary = compare()
    detail_path = EXTRACTED_DIR / "swmm_comparison_by_scenario.csv"
    summary_path = EXTRACTED_DIR / "swmm_comparison_summary.csv"
    details.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)
    print(summary.to_string(index=False))
    print(f"\nSaved: {detail_path}")
    print(f"Saved: {summary_path}")
