import argparse, json
from pathlib import Path
import pandas as pd

from model import load_network, evaluate_gbbrpm
from scenarios import run_core_scenarios
from comparators import compare_to_gbbrpm
from robustness import perturbation_trials, summarize_robustness
from property_tests import run_property_tests
from scalability import run_scalability

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RESULTS = HERE / "results"


def manifest():
    return json.loads((DATA / "network_manifest.json").read_text())


def run_core(networks, data_source):
    m = manifest()
    rows = []
    
    for name in networks:
        nodes, edges = load_network(name, source=data_source)
        outlet = m[name]["outlet"]
        risk, q = evaluate_gbbrpm(nodes, edges)
        pd.DataFrame({"node": list(risk), "R": list(risk.values())}).to_csv(
            RESULTS / f"{name}_baseline_node_risk.csv", index=False
        )

        q.to_csv(RESULTS / f"{name}_baseline_edge_contributions.csv", index=False)
        rows += run_core_scenarios(name, nodes, edges, outlet)

    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "core_scenarios.csv", index=False)

    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", choices=["core", "full"], default="full")
    p.add_argument("--networks", nargs="*", default=["N1", "N2", "N3", "N4", "N5"])
    p.add_argument("--trials", type=int, default=100)
    p.add_argument("--seed", type=int, default=41)
    p.add_argument(
        "--data-source",
        choices=["historical", "recovered"],
        default="historical",
    )

    a = p.parse_args()
    RESULTS.mkdir(exist_ok=True)

    core = run_core(a.networks, a.data_source)
    print(f"[core] {len(core)} scenario rows")

    if a.suite == "full":
        n, e = load_network("N5", source=a.data_source)
        comp = compare_to_gbbrpm(n, e)
        comp.to_csv(RESULTS / "N5_comparators.csv", index=False)
        print("[comparators]")
        print(comp.to_string(index=False))

        summaries = []
        
        for pct in (0.05, 0.10, 0.20):
            df = perturbation_trials(n, e, pct, a.trials, a.seed)
            df.to_csv(RESULTS / f"N5_robustness_{int(pct*100)}pct.csv", index=False)
            summaries.append(summarize_robustness(df))

        rs = pd.DataFrame(summaries)
        rs.to_csv(RESULTS / "N5_robustness_summary.csv", index=False)
        print("[robustness]")
        print(rs.to_string(index=False))

        prop = run_property_tests(a.trials, a.seed)
        prop.to_csv(RESULTS / "property_tests.csv", index=False)
        ps = pd.DataFrame(
            [
                {
                    "trials": len(prop),
                    "bounded_pass": int(prop.bounded.sum()),
                    "monotone_B_pass": int(prop.monotone_B.sum()),
                    "B1_implies_R1_pass": int(prop.B1_implies_R1.sum()),
                    "S0_gates_edge_pass": int(prop.S0_gates_edge.sum()),
                }
            ]
        )
        
        ps.to_csv(RESULTS / "property_tests_summary.csv", index=False)
        print("[property tests]")
        print(ps.to_string(index=False))

        sc = run_scalability()
        sc.to_csv(RESULTS / "scalability.csv", index=False)
        print("[scalability]")
        print(sc.to_string(index=False))

    print("\nDone:", RESULTS)


if __name__ == "__main__":
    main()
