import pandas as pd

from model import evaluate_gbbrpm
from metrics import spearman, topk, jaccard


def local_only(nodes):
    return {str(r.node): float(r.B) for r in nodes.itertuples(index=False)}


def uniform(nodes, edges, S):
    e = edges.copy()
    e["C"] = 1.0
    e["L"] = float(S)
    e["tau"] = 1.0

    return evaluate_gbbrpm(nodes, e)[0]


def compare_to_gbbrpm(nodes, edges, uniform_values=(0.25, 0.50, 0.75), k=3):
    base = evaluate_gbbrpm(nodes, edges)[0]
    bt = topk(base, k)
    rows = []
    loc = local_only(nodes)
    rows.append(
        {
            "comparator": "local_only",
            "spearman": spearman(base, loc),
            f"top{k}_jaccard": jaccard(bt, topk(loc, k)),
        }
    )

    for s in uniform_values:
        r = uniform(nodes, edges, s)
        rows.append(
            {
                "comparator": f"uniform_S_{s:.2f}",
                "spearman": spearman(base, r),
                f"top{k}_jaccard": jaccard(bt, topk(r, k)),
            }
        )
        
    return pd.DataFrame(rows)
