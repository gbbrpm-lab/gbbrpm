# Reproducible paper outputs

Run the publication-output layer after reproducing or updating the frozen
domain results:

```bash
python scripts/generate_paper_outputs.py
```

The command writes vector PDF figures, 300-dpi PNG previews, `booktabs` LaTeX
tables, and a hash manifest under `results/paper/`. The generator reads frozen
CSV and JSON inputs only; it does not rerun the model or retrieve remote data.

## Generated figures

- `fig_drainage_robustness`: N5 ranking stability under susceptibility
  perturbations;
- `fig_drainage_swmm_alignment`: SWMM rank and priority-set comparison;
- `fig_software_tau_sensitivity`: software risk response to transmission;
- `fig_software_vulnerable_subgraph`: vulnerable package propagation paths;
- `fig_electrical_topology_overview`: active nominal topology with instrumented
  buses; and
- `fig_electrical_baseline_coverage`: timestamp coverage by mapped meter.

## Generated tables

The tables cover the drainage evaluation networks, SWMM comparison, software
vulnerability inputs and transmission sweep, electrical baseline quality,
pending event windows, and the distinct evidentiary roles of all three domains.

Electrical outputs are intentionally labeled as baseline/importer evidence.
They must not be described as completed event-response validation until the
authorized event-centered measurements are processed and compared with a
separately parameterized GBBRPM instance.
