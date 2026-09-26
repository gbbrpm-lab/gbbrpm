#!/usr/bin/env python3
"""Build a frozen, time-aware electrical topology feasibility package."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from electrical_case import (  # noqa: E402
    build_topology_tables,
    group_status_events,
    load_topology_source,
    sha256,
    topology_diagnostics,
)


DEFAULT_SNAPSHOT = "2024-11-14T07:00:00"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology-source", type=Path, required=True)
    parser.add_argument("--snapshot-time", default=DEFAULT_SNAPSHOT)
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=ROOT / "data" / "electrical" / "socal28_sample",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.topology_source.resolve()
    case_dir = args.case_dir.resolve()
    case_dir.mkdir(parents=True, exist_ok=True)

    frozen_source = case_dir / "source_topology.zip"
    if source_path.suffix.lower() == ".zip" and source_path != frozen_source:
        shutil.copyfile(source_path, frozen_source)
        source_for_build = frozen_source
    else:
        source_for_build = source_path

    source = load_topology_source(source_for_build)
    nodes, edges, meter_mapping, events = build_topology_tables(
        source, args.snapshot_time
    )
    active_edges = edges.loc[edges["active"]].copy()

    nodes.to_csv(case_dir / "nodes.csv", index=False)
    edges.to_csv(case_dir / "all_edges.csv", index=False)
    active_edges.to_csv(case_dir / "active_edges.csv", index=False)
    meter_mapping.to_csv(case_dir / "meter_mapping.csv", index=False)
    events.to_csv(case_dir / "status_events.csv", index=False)
    event_groups = group_status_events(events)
    request_windows = event_groups.copy()
    if not request_windows.empty:
        request_windows["recommended_query_start"] = (
            pd.to_datetime(request_windows["start_time"]) - pd.Timedelta(minutes=5)
        ).map(pd.Timestamp.isoformat)
        request_windows["recommended_query_end"] = (
            pd.to_datetime(request_windows["end_time"]) + pd.Timedelta(minutes=5)
        ).map(pd.Timestamp.isoformat)
    request_windows.to_csv(case_dir / "event_request_windows.csv", index=False)

    diagnostics = topology_diagnostics(nodes, active_edges)
    graph = nx.from_pandas_edgelist(
        active_edges, "source", "target", create_using=nx.DiGraph
    )
    graph.add_nodes_from(nodes["node"])
    manifest = {
        "case_id": "electrical_socal28_public_sample",
        "role": "topology and baseline preprocessing; event validation pending",
        "snapshot_time": args.snapshot_time,
        "source_archive": frozen_source.name if frozen_source.exists() else source_path.name,
        "source_sha256": sha256(frozen_source if frozen_source.exists() else source_path),
        "network_member": source.network_member,
        "direction_semantics": "nominal fbus-to-tbus orientation; measured power-flow direction not yet verified",
        "active_rule": "NO is open/inactive; NC or unspecified transfer equipment is active",
        "transfer_equipment_record_count": int(len(edges)),
        "measurement_mapping_count": int(len(meter_mapping)),
        "distinct_measurement_file_count": int(
            meter_mapping["data_file"].replace("", pd.NA).dropna().nunique()
        ),
        "measurement_kind_counts": {
            str(kind): int(count)
            for kind, count in meter_mapping.groupby("measurement_kind").size().items()
        },
        "voltage_response_eligible_mapping_count": int(
            meter_mapping["voltage_response_eligible"].fillna(False).astype(bool).sum()
        ),
        "derived_or_signed_voltage_mapping_count": int(
            (
                meter_mapping["measurement_semantics"]
                == "derived_or_signed_voltage_channel"
            ).sum()
        ),
        "documented_status_transition_count": int(len(events)),
        "documented_event_group_count": int(len(event_groups)),
        "gbbrpm_execution_status": "not run: event-centered measurements and electrical S/B mapping pending",
        **diagnostics,
    }
    with (case_dir / "manifest.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(
        f"Electrical topology built at {args.snapshot_time}: "
        f"{len(nodes)} buses, {len(active_edges)} active edge records, "
        f"{len(events)} documented status transitions."
    )
    print(f"Nominal-orientation DAG: {manifest['dag_in_nominal_orientation']}")
    print(f"Case data: {case_dir}")


if __name__ == "__main__":
    main()
