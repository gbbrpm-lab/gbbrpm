# Software dependency feasibility case

## Purpose

This case tests whether the frozen GBBRPM v1 propagation core can be
instantiated on a real, nonphysical directed dependency network without
changing its aggregation equation. It is a cross-domain feasibility and
structural-behavior case. It is not presented as independent empirical
validation of downstream software failures.

## Frozen sources

- Root package: `npm:express@4.18.2`.
- Topology: exact resolved dependency response from deps.dev.
- Local evidence: exact package-version matches returned by OSV.
- Retrieval snapshot: `data/software/express_4.18.2/osv_snapshot.json`.
- Provenance and hashes: `data/software/express_4.18.2/manifest.json`.

The frozen dependency graph has 71 package-version nodes, 128 relations, one
weakly connected component, and no directed cycle. Package-version identity
uses `(ecosystem, name, version)`, so different resolved versions of the same
package remain distinct nodes.

## Direction conversion

deps.dev returns an edge from a dependent package to the dependency it uses:

```text
dependent -> dependency
```

For disturbance propagation, the case reverses that relation:

```text
dependency -> dependent
```

The conversion preserves acyclicity for this frozen graph. No edge is removed,
collapsed, or manually rewired.

## Domain mapping

### Nodes and local disturbance

Each node is one exact npm package version. OSV is queried with the exact
package name and version. If several advisories match, `B` uses the maximum
categorical severity mapping:

| OSV/GHSA severity | `B` |
| --- | ---: |
| None or unknown | 0.00 |
| Low | 0.25 |
| Moderate/medium | 0.50 |
| High | 0.75 |
| Critical | 1.00 |

This is an ordinal normalization convention for the feasibility case. It is
not a failure probability and is not claimed to be a calibrated conversion
from vulnerability severity to realized software impact.

### Relations and transmission

Every resolved dependency relation is assigned `S=1`. This encodes the
presence of a relation without asserting that optionality, runtime
reachability, exploitability, or call-path frequency has been measured.

No empirical source in this package calibrates `tau`. The case therefore
reports a uniform sensitivity sweep at `0`, `.25`, `.50`, `.75`, and `1.00`
instead of selecting one value as ground truth.

## Frozen evidence and observed behavior

The OSV snapshot contains 13 advisory matches across seven exact versions:

- `express@4.18.2`
- `body-parser@1.20.1`
- `cookie@0.5.0`
- `path-to-regexp@0.1.7`
- `qs@6.11.0`
- `send@0.18.0`
- `serve-static@1.15.0`

All seven are the root or direct dependencies in this resolved graph. Thus,
positive modeled risk is limited to those seven nodes, with multiple incoming
disturbances aggregating at the Express root. The remaining graph still
supports topology validation, but it does not provide an observed long
transitive vulnerability chain.

## Reporting boundary

The case supports claims about:

- successful conversion of a real dependency graph;
- direct domain-supplied susceptibility;
- boundedness and deterministic topological evaluation;
- multi-source aggregation at a dependent package;
- sensitivity of scores and rankings to uniform transmission values.

It does not independently establish that GBBRPM scores predict exploit
occurrence, incident severity, runtime reachability, or downstream service
failure. OSV is used to construct `B`; it is not reused as an independent
reference outcome.

## Reproduction

```bash
python scripts/build_software_case.py \
  --dependencies-json path/to/express_dependencies.json
python tests/software_case_test.py
```

Use `--refresh-osv` only when intentionally creating and documenting a newer
evidence snapshot. Normal reproduction reuses the frozen snapshot.
