# Reproducibility Status

Verified on 2026-09-19 from a clean Python virtual environment.

## Commands

```bash
pip install -r requirements.txt
python tests/smoke_test.py
python tests/reproducibility_test.py
python tests/swmm_reference_test.py
python run_experiments.py --data-source historical --trials 600 --seed 41
python scripts/run_swmm_and_extract.py
python scripts/compare_swmm_reference.py
```

## Verified results

- All five historical networks load and produce bounded node states.
- The controlled scenario suite contains 136 rows.
- The N5 comparator correlations reproduce the preserved values.
- All four property checks pass in 600 of 600 randomized trials.
- Robustness summaries reproduce the Chapter 4 values at all three
  perturbation levels.
- The path-pruned diagnostic reproduces the N3, N4, and N5 overlap-inflation
  values to six decimal places.
- The SWMM solver runs all 12 blockage scenarios and refreshes the stored node
  hydraulic results.
- The explicit SWMM comparison reproduces mean outside-downstream-scope shares
  of approximately 0.7120 for maximum-depth worsening and 0.4053 for
  flooding-volume worsening.

## Archived SWMM ranking metrics

The thesis contains archived SWMM rank-correlation and top-3 Jaccard values
whose original calculation script and complete ranking rule were not present
in the recovered repository. They are not silently relabeled as regenerated.
The current `scripts/compare_swmm_reference.py` states and executes one
complete protocol, and its generated summary is the reproducible result of
that protocol. The archived values should remain labeled historical unless
their original calculation artifact is recovered.

## Timing interpretation

`scalability.csv` now reports the median and interquartile range in addition
to the mean, minimum, and maximum over 30 timed repetitions after five warm-up
runs. Runtime values remain machine- and load-dependent; the median is the
preferred descriptive value when isolated scheduling outliers occur.
