# GBBRPM v1 Experiment Package

Reproducible experiment pipeline for the **Graph-Based Blockage Risk
Propagation Model (GBBRPM) v1**.

The package runs baseline evaluation, controlled scenario sweeps,
comparators, robustness and property tests, scalability experiments, and a
separate SWMM external-reference workflow.

## Contents

- [Model](#model)
- [Data and provenance](#data-and-provenance)
- [Setup](#setup)
- [Running experiments](#running-experiments)
- [Controlled scenario suite](#controlled-scenario-suite)
- [Outputs](#outputs)
- [SWMM external reference](#swmm-external-reference)
- [Reproducibility notes](#reproducibility-notes)
- [Repository structure](#repository-structure)
- [Scope and limitations](#scope-and-limitations)

## Model

GBBRPM v1 requires a directed acyclic graph (DAG) and evaluates nodes in
topological order. For a directed edge `i -> j`:

$$
Q_{ij} = S_{ij}\tau_{ij}R_i
$$

where:

- `R_i` is the current propagated risk at the upstream node.
- `S_ij` is the edge susceptibility.
- `tau_ij` is the transmission factor.
- `Q_ij` is the incoming risk contribution.

For the baseline drainage instantiation:

$$
S_{ij} = \min\left(1,\frac{L_{ij}}{C_{ij}}\right),
\qquad \tau_{ij}=1
$$

The receiving-node update is:

$$
R_j = 1 - (1-B_j)\prod_{i \in P(j)}(1-Q_{ij})
$$

`B_j` is the local blockage or disturbance severity. `R` is a bounded,
normalized continuous **risk index**, not a probability.

## Data and provenance

The repository preserves three distinct data groups. The default data source
is `historical`.

| Data source | Location | Role |
| --- | --- | --- |
| Historical validation inputs | `data/historical/` | Reconstructed inputs used for the preserved historical validation behavior. |
| Recovered historical candidate | `data/recovered_candidate/` | Alternate historical artifact retained for comparison and provenance analysis. |
| Reconstructed package fixtures | `data/reconstructed/` | Fallback fixtures retained for provenance and comparison. |

### Historical validation inputs

The historical files are:

- `validation_reconstructed_edges.csv`
- `validation_reconstructed_nodes.csv`

They have been computationally verified against the preserved historical
validation behavior. With the current frozen implementation, they reproduce:

- N5 outlet risk near `0.70864`.
- The N5 ranking `N13 > N19 > N16`.
- Historical comparator behavior.
- The restored 136-scenario controlled experiment suite.

These should be described as **historical reconstructed validation inputs
that reproduce the preserved historical validation results**. They should
not be represented as the lost original raw edge-by-edge historical dataset
unless stronger provenance evidence is recovered.

### Recovered historical candidate

The files under `data/recovered_candidate/` contain combined N1-N5 node,
edge, and network-summary tables recovered from older thesis files. They
produce different numerical results from the reconstructed historical
validation inputs, so they are retained as an alternate dataset rather than
the default thesis reproduction source.

### Selecting a data source

Use `--data-source historical` for historical validation reproduction or
`--data-source recovered` for the alternate dataset. The default is
`historical`.

## Setup

### Windows / PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_experiments.py --data-source historical
```

### WSL / Ubuntu

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_experiments.py --data-source historical
```

## Running experiments

Run the full historical validation suite:

```bash
python run_experiments.py --data-source historical
```

Run only the controlled scenario suite:

```bash
python run_experiments.py --suite core --data-source historical
```

Run the historical suite with 600 robustness/property trials:

```bash
python run_experiments.py --data-source historical --trials 600 --seed 41
```

Run selected networks only:

```bash
python run_experiments.py \
  --suite core \
  --data-source historical \
  --networks N3 N5
```

Use the recovered alternate dataset:

```bash
python run_experiments.py --data-source recovered
```

Inspect saved outputs and run the smoke test:

```bash
python inspect_results.py
python tests/smoke_test.py
```

## Controlled scenario suite

The restored historical core suite contains 136 scenario runs.

| Scenario family | Runs | Protocol |
| --- | ---: | --- |
| Source severity | 20 | Four severity levels across five networks. |
| L/C stress | 25 | Five load-scaling levels across five networks. |
| Blockage location | 36 | Selected blockage locations from the historical protocol. |
| Source combination | 10 | Multi-source configurations for N3 and N5. |
| Intermediate blockage | 45 | Three selected nodes, three severities, across five networks. |
| **Total** | **136** | |

### Sweep levels

- **Source severity:** `0.25`, `0.50`, `0.75`, `1.00`.
- **L/C stress:** `0.50`, `0.75`, `1.00`, `1.25`, `1.50`.
- **Intermediate blockage:** `0.25`, `0.50`, `0.75`.

The blockage-location sweep evaluates selected locations rather than every
node in every network.

### Additional validation blocks

The full suite also includes:

- N1-N5 baseline evaluation.
- Local-only and uniform-susceptibility comparators.
- Perturbation robustness at +/-5%, +/-10%, and +/-20%.
- Randomized boundedness and monotonicity tests.
- `B = 1 -> R = 1` boundary checks.
- `S = 0` edge-gating checks.
- Sparse-DAG scalability timing.

### Preserved validation behavior

The historical input configuration reproduces the preserved N5 comparator
behavior:

```text
local_only       ~=  0.1086
uniform_S_0.25  ~= -0.0421
uniform_S_0.50  ~=  0.1504
uniform_S_0.75  ~=  0.6962
```

The historical N5 baseline also reproduces N20 outlet risk near `0.70864`,
with the key ranking `N13 > N19 > N16`.

Robustness tail statistics and timing may vary slightly with implementation
details, random sampling order, operating-system load, and runtime
environment.

## Outputs

Generated files are written under `results/`. Important outputs include:

- `core_scenarios.csv`
- `N5_comparators.csv`
- `N5_robustness_summary.csv`
- `property_tests_summary.csv`
- `scalability.csv`
- `N*_baseline_node_risk.csv`
- `N*_baseline_edge_contributions.csv`

## SWMM external reference

The SWMM workflow is separate from the internal GBBRPM experiment suite.
Its files are under `data/swmm/`, with blockage scenarios in
`data/swmm/scenarios/` and extracted hydraulic results in
`data/swmm/extracted/`.

Run the SWMM workflow with:

```bash
python scripts/run_swmm_and_extract.py
```

SWMM is used as an external hydraulic reference to examine:

- Where propagated-risk rankings agree with hydraulic consequences.
- Where those rankings diverge.
- Which hydraulic behaviors lie outside the downstream-only GBBRPM v1
  formulation.

The comparison treats GBBRPM as a lightweight, interpretable downstream
risk-propagation and prioritization surrogate, not as a replacement for a
hydraulic simulator.

## Reproducibility notes

Do not manually enter susceptibility values into the evaluator. For every
edge, susceptibility is recalculated from the primitive `L` and `C` inputs:

```text
u = L / C
S = min(1, u)
tau = 1
```

The evaluator validates:

- `C > 0`
- `L >= 0`
- `B in [0,1]`
- DAG structure
- Bounded risk contributions

Where stored `u` or `S` columns exist, they may be checked against values
recomputed from `L` and `C`.

## Repository structure

```text
gbbrpm/
├── data/
│   ├── historical/
│   ├── recovered_candidate/
│   ├── reconstructed/
│   └── swmm/
├── results/
├── scripts/
├── tests/
├── model.py
├── scenarios.py
├── run_experiments.py
├── inspect_results.py
└── requirements.txt
```

## Branch naming convention

Use these prefixes:

```text
feature/<short-description>
fix/<short-description>
docs/<short-description>
test/<short-description>
experiment/<short-description>
analysis/<short-description>
```

Examples include `feature/result-export`, `fix/csv-loader`,
`docs/readme-cleanup`, `experiment/lc-sweep`, and
`analysis/ranking-stability`.

## Scope and limitations

GBBRPM v1 is intended as a lightweight and interpretable graph-based
risk-propagation model. It does not currently model:

- Full hydraulic dynamics.
- Backwater effects.
- Bidirectional flow.
- Surcharge and ponding feedback.
- Common-cause or shared-path dependence correction.
- Calibrated heterogeneous transmission factors.

The baseline implementation therefore supports mechanism analysis, scenario
comparison, and prioritization rather than high-fidelity physical
simulation.