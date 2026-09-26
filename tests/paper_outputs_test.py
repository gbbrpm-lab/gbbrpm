"""Verify committed publication outputs and their provenance hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "results" / "paper"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


with (OUTPUT_ROOT / "paper_outputs_manifest.json").open(encoding="utf-8") as handle:
    manifest = json.load(handle)

expected_figure_stems = {
    "fig_drainage_robustness",
    "fig_drainage_swmm_alignment",
    "fig_software_tau_sensitivity",
    "fig_software_vulnerable_subgraph",
    "fig_electrical_topology_overview",
    "fig_electrical_baseline_coverage",
}
expected_tables = {
    "table_cross_domain_evidence.tex",
    "table_drainage_networks.tex",
    "table_drainage_swmm.tex",
    "table_software_sensitivity.tex",
    "table_software_vulnerabilities.tex",
    "table_electrical_baseline.tex",
    "table_electrical_data_quality.tex",
    "table_electrical_event_windows.tex",
}

figure_paths = [ROOT / item["path"] for item in manifest["figures"]]
table_paths = [ROOT / item["path"] for item in manifest["tables"]]
assert len(figure_paths) == 12
assert len(table_paths) == 8
assert {path.stem for path in figure_paths} == expected_figure_stems
assert {path.name for path in table_paths} == expected_tables

for section in ("figures", "tables"):
    for item in manifest[section]:
        path = ROOT / item["path"]
        assert path.exists() and path.stat().st_size > 0
        assert sha256(path) == item["sha256"]

for relative_path, expected_hash in manifest["input_sha256"].items():
    path = ROOT / relative_path
    assert path.exists()
    assert sha256(path) == expected_hash

for table in table_paths:
    text = table.read_text(encoding="utf-8")
    assert "\\toprule" in text and "\\bottomrule" in text
    assert "Auto-generated" in text

print("Publication-output hashes and inventory checks passed.")
