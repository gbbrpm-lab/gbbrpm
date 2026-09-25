import pandas as pd

from model import evaluate_gbbrpm
from metrics import jaccard, percentile_priority_set, spearman


def local_only(nodes):
    return {str(r.node): float(r.B) for r in nodes.itertuples(index=False)}


def uniform(nodes, edges, S):
    e = edges.copy()
    e["C"] = 1.0
    e["L"] = float(S)
    e["tau"] = 1.0

    return evaluate_gbbrpm(nodes, e)[0]


def compare_to_gbbrpm(
    nodes,
    edges,
    uniform_values=(0.25, 0.50, 0.75),
    priority_fraction=0.20,
):
    base = evaluate_gbbrpm(nodes, edges)[0]
    base_priority, nominal_k, _ = percentile_priority_set(base, priority_fraction)
    label = f"top_{int(round(priority_fraction * 100))}pct_jaccard"
    rows = []
    loc = local_only(nodes)
    rows.append(
        {
            "comparator": "local_only",
            "priority_fraction": priority_fraction,
            "priority_k_nominal": nominal_k,
            "spearman": spearman(base, loc),
            label: jaccard(
                base_priority,
                percentile_priority_set(loc, priority_fraction)[0],
            ),
        }
    )

    for s in uniform_values:
        r = uniform(nodes, edges, s)
        rows.append(
            {
                "comparator": f"uniform_S_{s:.2f}",
                "priority_fraction": priority_fraction,
                "priority_k_nominal": nominal_k,
                "spearman": spearman(base, r),
                label: jaccard(
                    base_priority,
                    percentile_priority_set(r, priority_fraction)[0],
                ),
            }
        )
        
    return pd.DataFrame(rows)
