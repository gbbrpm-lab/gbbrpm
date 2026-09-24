import numpy as np
import pandas as pd
from math import ceil


def ranked_items(risk):
    """Return a deterministic descending ranking; node ID orders exact ties."""
    return sorted(risk.items(), key=lambda kv: (-float(kv[1]), str(kv[0])))


def percentile_priority_set(risk, fraction=0.20):
    """Return the top fraction of positive-risk nodes and retain cutoff ties."""
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    if not risk:
        return set(), 0, float("nan")

    items = ranked_items(risk)
    k = max(1, ceil(fraction * len(items)))
    cutoff = float(items[k - 1][1])
    selected = {str(node) for node, score in items if score > 0 and score >= cutoff}
    return selected, k, cutoff


def priority_set(risk, fraction=0.20):
    """Convenience wrapper returning only the tie-aware selected node set."""
    return percentile_priority_set(risk, fraction)[0]


def summarize(risk, outlet=None, threshold=0.05, priority_fraction=0.20):
    items = ranked_items(risk)
    vals = np.array(list(risk.values()), float)
    priority, nominal_k, cutoff = percentile_priority_set(risk, priority_fraction)
    pct = int(round(priority_fraction * 100))

    return {
        "max_risk": float(vals.max()),
        "mean_risk": float(vals.mean()),
        "affected_nodes": int((vals > threshold).sum()),
        "top_node": items[0][0],
        "priority_fraction": float(priority_fraction),
        "priority_k_nominal": nominal_k,
        "priority_count_with_ties": len(priority),
        "priority_cutoff": cutoff,
        f"top_{pct}pct": "|".join(node for node, _ in items if node in priority),
        "outlet_risk": float(risk[outlet]) if outlet in risk else np.nan,
    }


def spearman(a, b):
    keys = sorted(set(a) & set(b))
    ra = pd.Series([a[k] for k in keys]).rank(method="average").to_numpy(float)
    rb = pd.Series([b[k] for k in keys]).rank(method="average").to_numpy(float)

    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")

    return float(np.corrcoef(ra, rb)[0, 1])


def jaccard(a, b):
    return 1.0 if not a and not b else len(a & b) / len(a | b)
