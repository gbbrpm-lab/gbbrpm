#!/usr/bin/env python3
"""Summarize a large magnitude ZIP locally without extracting every CSV."""

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

from electrical_case import sha256, summarize_magnitude_archive  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--magnitudes-zip", type=Path, required=True)
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=ROOT / "data" / "electrical" / "socal28_sample",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "electrical" / "socal28_sample",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        help="Development/testing limit; omit to summarize every CSV.",
    )
    parser.add_argument(
        "--skip-archive-hash",
        action="store_true",
        help="Skip the additional full-archive pass used to compute SHA-256.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archive = args.magnitudes_zip.resolve()
    case_dir = args.case_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = pd.read_csv(case_dir / "meter_mapping.csv")
    summary = summarize_magnitude_archive(
        archive,
        mapping,
        max_files=args.max_files,
    )
    output_path = output_dir / "baseline_channel_summary.csv"
    summary.to_csv(output_path, index=False)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_archive_name": archive.name,
        "source_archive_sha256": (
            None if args.skip_archive_hash else sha256(archive)
        ),
        "summarized_file_count": int(len(summary)),
        "mapped_file_count": int((summary["measurement_kind"] != "unmapped").sum()),
        "unmapped_file_count": int((summary["measurement_kind"] == "unmapped").sum()),
        "explicit_alias_match_count": int(
            (summary["mapping_method"] == "explicit_source_filename_alias").sum()
        ),
        "explicit_alias_matches": [
            {
                "archive_data_file": str(row.data_file),
                "declared_data_file": str(row.declared_data_file),
            }
            for row in summary.loc[
                summary["mapping_method"] == "explicit_source_filename_alias"
            ].itertuples(index=False)
        ],
        "populated_file_count": int((summary["data_status"] == "populated").sum()),
        "empty_file_count": int((summary["data_status"] == "empty").sum()),
        "voltage_response_eligible_file_count": int(
            summary["voltage_response_eligible"].fillna(False).astype(bool).sum()
        ),
        "missing_value_count": int(summary["missing_value_count"].sum()),
        "invalid_timestamp_count": int(summary["invalid_timestamp_count"].sum()),
        "duplicate_timestamp_count": int(summary["duplicate_timestamp_count"].sum()),
        "out_of_order_timestamp_count": int(
            summary["out_of_order_timestamp_count"].sum()
        ),
        "missing_timestamp_count": int(summary["missing_timestamp_count"].sum()),
        "timestamp_coverage_fraction": (
            float(
                (
                    summary["expected_timestamp_count"].sum()
                    - summary["missing_timestamp_count"].sum()
                )
                / summary["expected_timestamp_count"].sum()
            )
            if summary["expected_timestamp_count"].sum() > 0
            else None
        ),
        "earliest_measurement": (
            str(summary["start_time"].dropna().min()) if len(summary) else None
        ),
        "latest_measurement": (
            str(summary["end_time"].dropna().max()) if len(summary) else None
        ),
        "max_files_limit": args.max_files,
        "role": "normal-operation baseline and importer verification; not event-response validation",
        "missingness_semantics": (
            "missing_value_count counts invalid/blank values in present rows; "
            "missing_timestamp_count counts absent intervals at each channel's "
            "inferred modal sampling cadence"
        ),
        "voltage_normalization_rule": (
            "per-unit values and event rankings use only direct phase-to-ground "
            "voltage magnitude registers; derived or signed voltage expressions "
            "are retained as raw summaries but excluded"
        ),
        "mapping_rule": (
            "exact declared data_file match first; then the documented CT16-to-C16 "
            "source filename aliases; unmatched archive files remain visible as unmapped"
        ),
    }
    with (output_dir / "baseline_manifest.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"Saved {len(summary)} channel summaries: {output_path}")


if __name__ == "__main__":
    main()
