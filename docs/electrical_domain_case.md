# Electrical distribution case: preprocessing and validation plan

## Current evidentiary role

The public SoCal distribution sample is used as a second non-drainage domain
for testing whether the GBBRPM data contract can be instantiated on a real,
documented network. The currently available files establish topology,
time-varying switch states, meter-to-element mapping, and a normal-operation
magnitude baseline. They do **not** yet establish independent event-response
validation of GBBRPM.

The topology archive is frozen under
`data/electrical/socal28_sample/source_topology.zip`. At the declared snapshot
of `2024-11-14T07:00:00`, the converter produces 187 bus records, 203 transfer
equipment records, and 177 active directed connections. The nominal
`fbus -> tbus` orientation is acyclic. This orientation comes from the source
topology and has not yet been verified against measured power-flow direction.

## Deterministic conversion

`scripts/build_electrical_case.py` resolves each time-series switch state at
the requested snapshot, excludes normally open equipment, and writes:

- `nodes.csv`: bus identifiers and available nominal voltage metadata;
- `all_edges.csv`: every transfer-equipment relation and resolved state;
- `active_edges.csv`: relations active at the snapshot;
- `meter_mapping.csv`: measurement files mapped to elements and units;
- `status_events.csv`: documented state transitions; and
- `event_request_windows.csv`: operation groups with recommended five-minute
  download padding on both sides; and
- `manifest.json`: source hash, snapshot, counts, and interpretation limits.

The snapshot contains 226 register mappings representing 222 distinct named
measurement files. The status series contain 34 transitions grouped into 12
event windows under the declared 60-second grouping rule.

## Baseline magnitude archive

The separately downloaded magnitude ZIP covers approximately
`2024-11-14T07:00:00` through `2024-11-15T07:00:00`. Because the latest
documented switching sequence occurred on `2024-11-13`, this archive is used
only to verify ingestion, units, coverage, and normal-operation summaries. It
must not be presented as switching-event outcome validation.

Run the streaming summarizer locally without extracting the full archive:

```bash
python scripts/summarize_electrical_baseline.py \
  --magnitudes-zip path/to/magnitudes.zip
```

It writes `baseline_channel_summary.csv` and `baseline_manifest.json` under
`results/electrical/socal28_sample/`. The summary reports coverage, missing
values, quantiles, dispersion, and voltage mean in per-unit form where a
nominal voltage is mapped.

## Event-response analysis after approval

When the requested event-centered measurements are available, place their CSV
files in one or more directories or ZIP archives and run:

```bash
python scripts/analyze_electrical_events.py \
  --measurements path/to/event_opening path/to/event_restoration
```

For each documented operation group, the script compares median measurements
in a 60-second pre-event window and a 60-second post-event window, separated
from the operation by a five-second guard interval. Voltage responses are
normalized by nominal voltage; power responses retain both absolute and
relative change. Bus-level voltage response is the maximum phase-channel
change. The script reports the complete ranking and a tie-aware top-20%
priority set, consistent with the generic reporting convention.

This observed-response ranking is an independent comparison target. A later
GBBRPM instantiation must separately declare and justify electrical meanings
for local disturbance `B`, susceptibility `S`, and transmission `tau` before
model predictions are compared with it. The topology importer intentionally
does not invent these quantities.

## Remaining validation gates

The electrical case can support a Chapter 4 validation claim only after:

1. event-centered measurements cover at least one documented switching group;
2. the direction used for propagation is checked against the event or power
   measurements;
3. the mappings for `B`, `S`, and `tau` are specified without using the same
   observed outcome later treated as ground truth;
4. the model ranking is compared with the independently computed observed
   response ranking using the complete-ranking and tie-aware top-20% rules;
5. uncovered events, missing channels, and disconnected buses are reported;
   and
6. all source files, time windows, hashes, and transformation settings are
   preserved in manifests.

Until those gates are met, this case is accurately described as a real-data
feasibility and preprocessing result, not completed predictive validation.
