from pathlib import Path
import re
import pandas as pd

try:
    from swmm.toolkit import solver
except ImportError:
    raise SystemExit("Install swmm-toolkit first: pip install swmm-toolkit")

REPO_ROOT = Path(__file__).resolve().parents[1]
SWMM_DIR = REPO_ROOT / "data" / "swmm"
SCENARIO_DIR = SWMM_DIR / "scenarios"
EXTRACTED_DIR = SWMM_DIR / "extracted"
manifest = pd.read_csv(SWMM_DIR / "scenario_manifest.csv")


def run(inp):
    rpt = inp.with_suffix(".rpt")
    out = inp.with_suffix(".out")
    solver.swmm_run(str(inp), str(rpt), str(out))
    return rpt


def parse_node_depth_summary(rpt):
    text = rpt.read_text(errors="ignore")
    # SWMM report section: Node Depth Summary
    m = re.search(
        r"Node Depth Summary(.*?)(?=\n\s*\*+\s*\n\s*Node Inflow Summary)",
        text,
        re.S | re.I,
    )
    rows = []
    if not m:
        return pd.DataFrame()
    for line in m.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 7 and re.match(r"^N\d+$", parts[0]):
            try:
                rows.append(
                    {
                        "Node": parts[0],
                        "AvgDepth": float(parts[2]),
                        "MaxDepth": float(parts[3]),
                        "MaxHGL": float(parts[4]),
                    }
                )
            except:
                pass
    return pd.DataFrame(rows)


def parse_node_flooding(rpt):
    text = rpt.read_text(errors="ignore")
    m = re.search(
        r"Node Flooding Summary(.*?)(?=\n\s*\*+\s*\n\s*Outfall Loading Summary)",
        text,
        re.S | re.I,
    )
    rows = []
    if not m:
        return pd.DataFrame(
            columns=["Node", "FloodHours", "MaxFloodRate", "FloodVolume"]
        )
    for line in m.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 6 and re.match(r"^N\d+$", parts[0]):
            try:
                rows.append(
                    {
                        "Node": parts[0],
                        "FloodHours": float(parts[1]),
                        "MaxFloodRate": float(parts[2]),
                        "FloodVolume": float(parts[5]),
                    }
                )
            except:
                pass
    return pd.DataFrame(rows)


results = []
all_files = [SWMM_DIR / "N5_SWMM_base.inp"] + [
    SCENARIO_DIR / f for f in manifest["File"]
]
for inp in all_files:
    rpt = run(inp)
    d = parse_node_depth_summary(rpt)
    f = parse_node_flooding(rpt)
    if d.empty:
        print("Could not parse depth summary:", rpt)
        continue
    z = d.merge(f, on="Node", how="left").fillna(0)
    # Hydraulic reference score is intentionally NOT called probability.
    # Primary ranking variables remain separate: MaxDepth and FloodVolume.
    z["Scenario"] = inp.stem
    results.append(z)

if results:
    res = pd.concat(results, ignore_index=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    output = EXTRACTED_DIR / "swmm_hydraulic_results.csv"
    res.to_csv(output, index=False)
    print(
        res.groupby("Scenario").apply(
            lambda x: x.sort_values(["FloodVolume", "MaxDepth"], ascending=False).head(
                5
            )[["Node", "MaxDepth", "FloodVolume"]]
        )
    )
    print(f"\nSaved: {output}")
