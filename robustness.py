import numpy as np, pandas as pd

from model import evaluate_gbbrpm
from metrics import jaccard, percentile_priority_set, spearman


def perturbation_trials(
    nodes,
    edges,
    pct=0.05,
    trials=100,
    seed=41,
    priority_fraction=0.20,
):
    rng = np.random.default_rng(seed)
    baseline = evaluate_gbbrpm(nodes, edges)[0]
    baseline_priority, nominal_k, _ = percentile_priority_set(
        baseline, priority_fraction
    )
    label = f"top_{int(round(priority_fraction * 100))}pct_jaccard"
    rows = []

    for t in range(trials):
        n = nodes.copy()
        e = edges.copy()
        mask = n.B > 0
        
        if mask.any():
            n.loc[mask, "B"] = (
                n.loc[mask, "B"].to_numpy()
                * rng.uniform(1 - pct, 1 + pct, int(mask.sum()))
            ).clip(0, 1)

        e["L"] = (e.L.to_numpy() * rng.uniform(1 - pct, 1 + pct, len(e))).clip(0, None)
        e["C"] = (e.C.to_numpy() * rng.uniform(1 - pct, 1 + pct, len(e))).clip(
            1e-9, None
        )

        r = evaluate_gbbrpm(n, e)[0]
        perturbed_priority, _, _ = percentile_priority_set(r, priority_fraction)
        rows.append(
            {
                "pct": pct,
                "trial": t,
                "seed": seed,
                "priority_fraction": priority_fraction,
                "priority_k_nominal": nominal_k,
                "spearman": spearman(baseline, r),
                label: jaccard(baseline_priority, perturbed_priority),
            }
        )

    return pd.DataFrame(rows)


def summarize_robustness(df):
    priority_fraction = float(df.priority_fraction.iloc[0])
    c = f"top_{int(round(priority_fraction * 100))}pct_jaccard"
    return {
        "pct": float(df.pct.iloc[0]),
        "trials": len(df),
        "priority_fraction": priority_fraction,
        "priority_k_nominal": int(df.priority_k_nominal.iloc[0]),
        "mean_spearman": float(df.spearman.mean()),
        "p05_spearman": float(df.spearman.quantile(0.05)),
        "p95_spearman": float(df.spearman.quantile(0.95)),
        f"mean_{c}": float(df[c].mean()),
    }
