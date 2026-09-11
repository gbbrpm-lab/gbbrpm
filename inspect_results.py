from pathlib import Path
import pandas as pd

r = Path(__file__).resolve().parent / "results"

for name in [
    "core_scenarios.csv",
    "N5_comparators.csv",
    "N5_robustness_summary.csv",
    "property_tests_summary.csv",
    "scalability.csv",
]:
    p = r / name
    if p.exists():
        print("\n" + "=" * 70 + "\n" + name + "\n" + "=" * 70)
        print(pd.read_csv(p).to_string(index=False))
