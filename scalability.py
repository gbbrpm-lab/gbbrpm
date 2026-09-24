import time, numpy as np, pandas as pd

from model import evaluate_gbbrpm


def sparse_random_dag(n, edges_per_node=3, seed=41):
    rng = np.random.default_rng(seed + n)
    nodes = pd.DataFrame({"node": [f"v{i}" for i in range(n)], "B": 0.0})
    nodes.loc[0, "B"] = 0.75
    pairs = set()
    target = max(1, n * edges_per_node)
    attempts = 0

    while len(pairs) < target and attempts < target * 30:
        i = int(rng.integers(0, n - 1))
        j = int(rng.integers(i + 1, n))
        pairs.add((i, j))
        attempts += 1

    rows = []

    for i, j in sorted(pairs):
        C = float(rng.uniform(80, 120))
        L = float(rng.uniform(0.2, 0.9) * C)
        rows.append((f"v{i}", f"v{j}", C, L, 1.0))

    return nodes, pd.DataFrame(rows, columns=["source", "target", "C", "L", "tau"])


def run_scalability(
    sizes=(20, 50, 100, 250, 500, 1000),
    repeats=30,
    warmups=5,
    seed=41,
):
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    if warmups < 0:
        raise ValueError("warmups cannot be negative")

    rows = []

    for n in sizes:
        nodes, edges = sparse_random_dag(n, 3, seed)

        for _ in range(warmups):
            evaluate_gbbrpm(nodes, edges)

        times = []

        for _ in range(repeats):
            t0 = time.perf_counter()
            evaluate_gbbrpm(nodes, edges)
            times.append((time.perf_counter() - t0) * 1000)

        rows.append(
            {
                "nodes": n,
                "edges": len(edges),
                "mean_ms": float(np.mean(times)),
                "median_ms": float(np.median(times)),
                "q25_ms": float(np.percentile(times, 25)),
                "q75_ms": float(np.percentile(times, 75)),
                "min_ms": float(np.min(times)),
                "max_ms": float(np.max(times)),
                "repeats": repeats,
                "warmups": warmups,
            }
        )

    return pd.DataFrame(rows)
