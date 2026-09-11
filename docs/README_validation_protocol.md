# External Hydraulic-Reference Validation Protocol

Benchmark: US EPA SWMM, Dynamic Wave routing.

## Purpose
Evaluate whether GBBRPM produces node/component prioritizations that correspond to independently computed hydraulic stress patterns. This is a ranking/consequence correspondence test, not an equality test between the dimensionless GBBRPM risk index and hydraulic quantities.

## Independent hydraulic inputs
- N5 topology is preserved.
- Junction invert elevations decrease downstream.
- Circular conduit diameters and Manning roughness define hydraulic conveyance.
- Source hydrographs are imposed at N1, N2, and N3 as external inflows.
- SWMM computes flow, depth, surcharge, and flooding from these inputs.
- The old synthetic L/C values are NOT supplied to SWMM as solved hydraulic states.

## Blockage representation
A blockage scenario reduces the cross-sectional area of a selected conduit by 25%, 50%, or 75%. Equivalent circular diameter is scaled by sqrt(1 - blockage_area_fraction).

## Reference outcomes
Primary:
1. maximum node depth;
2. node flooding volume / flooding duration when present;
3. conduit peak flow and capacity utilization if extracted from the SWMM output.

## GBBRPM comparison
For each SWMM scenario:
1. derive conduit operating load L_ij from SWMM peak conduit flow;
2. derive effective capacity C_ij from the corresponding conduit full-flow capacity or a consistent SWMM/geometry-based capacity estimate;
3. compute S_ij = clip(L_ij/C_ij, 0, 1);
4. apply the same local blockage scenario in GBBRPM;
5. compare node rankings using Spearman rho, top-k overlap/Jaccard, and identification of hydraulically critical/flooded nodes.

## Interpretation
High rank agreement supports GBBRPM as a lightweight prioritization surrogate.
Low agreement identifies where dynamic hydraulic effects (backwater, surcharge, reverse flow, storage/ponding, dependence) exceed the graph model's abstraction.
Do not claim hydraulic predictive accuracy from synthetic agreement alone.
