#!/usr/bin/env python3
"""Create observed electrical response rankings around switching events."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from electrical_case import (  # noqa: E402
    analyze_event_responses,
    load_measurement_sources,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measurements",
        type=Path,
        nargs="+",
        required=True,
        help="One or more API output directories or ZIP archives.",
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=ROOT / "data" / "electrical" / "socal28_sample",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "electrical" / "socal28_sample" / "events",
    )
    parser.add_argument("--before-seconds", type=int, default=60)
    parser.add_argument("--after-seconds", type=int, default=60)
    parser.add_argument("--guard-seconds", type=int, default=5)
    parser.add_argument("--group-gap-seconds", type=int, default=60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    case_dir = args.case_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = pd.read_csv(case_dir / "meter_mapping.csv")
    events = pd.read_csv(case_dir / "status_events.csv")
    measurements = load_measurement_sources(
        [path.resolve() for path in args.measurements]
    )
    coverage, voltage, power, ranking = analyze_event_responses(
        measurements,
        mapping,
        events,
        before_seconds=args.before_seconds,
        after_seconds=args.after_seconds,
        guard_seconds=args.guard_seconds,
        group_gap_seconds=args.group_gap_seconds,
    )

    coverage.to_csv(output_dir / "event_coverage.csv", index=False)
    voltage.to_csv(output_dir / "observed_voltage_response.csv", index=False)
    power.to_csv(output_dir / "observed_power_response.csv", index=False)
    ranking.to_csv(output_dir / "observed_voltage_ranking.csv", index=False)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "measurement_sources": [path.name for path in args.measurements],
        "loaded_channel_count": len(measurements),
        "covered_event_group_count": (
            int(coverage["covered"].sum()) if not coverage.empty else 0
        ),
        "voltage_response_rows": len(voltage),
        "power_response_rows": len(power),
        "ranking_rows": len(ranking),
        "before_seconds": args.before_seconds,
        "after_seconds": args.after_seconds,
        "guard_seconds": args.guard_seconds,
        "group_gap_seconds": args.group_gap_seconds,
        "reference_role": "independent observed-response ranking; GBBRPM comparison is a later explicit step",
    }
    with (output_dir / "event_analysis_manifest.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(
        f"Loaded {len(measurements)} channels; "
        f"covered {manifest['covered_event_group_count']} event groups."
    )
    print(f"Event outputs: {output_dir}")


if __name__ == "__main__":
    main()
