# GBBRPM v1 Experiment Package

This package automates the Graph-Based Blockage Risk Propagation Model so you do not have to calculate scenarios node-by-node.

## Provenance note

The thesis workspace preserves the N1-N5 network sizes, structural purposes, source severities, scenario design, and summarized validation findings, but the original historical **edge-by-edge L/C table is not preserved** there.

Therefore, the CSVs in `data/` are **reconstructed test fixtures**. They are suitable for learning, checking the model, rerunning the experiment pipeline, and replacing with the original inputs later. They should **not** be cited as the exact inputs that produced previously reported historical numerical results.

## Frozen model

For edge `i -> j`:

`Q_ij = S_ij * tau_ij * R_i`

Baseline drainage susceptibility:

`S_ij = min(1, L_ij / C_ij)`

Receiving-node update:

`R_j = 1 - (1 - B_j) * product(1 - Q_ij)`

Baseline `tau_ij = 1`.

`R` is a bounded normalized continuous **risk index**, not a probability.

## Setup in VS Code

### Windows / PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_experiments.py
```

### WSL / Ubuntu

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_experiments.py
```

## Useful commands

Full suite:

```bash
python run_experiments.py
```

Core controlled scenarios only:

```bash
python run_experiments.py --suite core
```

Use 600 robustness/property trials:

```bash
python run_experiments.py --trials 600 --seed 41
```

Run only selected networks:

```bash
python run_experiments.py --suite core --networks N3 N5
```

Inspect saved outputs:

```bash
python inspect_results.py
```

Smoke test:

```bash
python tests/smoke_test.py
```

## Automated experiment blocks

- N1-N5 baseline evaluation
- source-severity sweep
- L/C stress sweep
- blockage-location sweep
- source-combination sweep for N3/N5
- intermediate-blockage sweep for N5
- local-only comparator
- uniform-susceptibility comparators
- perturbation robustness at ±5%, ±10%, ±20%
- randomized boundedness/monotonicity/boundary/property checks
- sparse-DAG scalability timing

## Input CSVs

`data/N*_nodes.csv`

Columns:
- `node`
- `B`

`data/N*_edges.csv`

Columns:
- `source`
- `target`
- `C`
- `L`
- `tau`

Do not manually enter `S`; the evaluator recalculates it from `L/C`.

## Main outputs

Generated under `results/`:

- `core_scenarios.csv`
- `N5_comparators.csv`
- `N5_robustness_summary.csv`
- `property_tests_summary.csv`
- `scalability.csv`
- `N*_baseline_node_risk.csv`
- `N*_baseline_edge_contributions.csv`

## Exact historical reproduction

If you recover the original edge-level `L` and `C` values, replace the matching CSVs in `data/`. The experiment code itself does not need to change.
