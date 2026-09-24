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
        "earliest_measurement": (
            str(summary["start_time"].dropna().min()) if len(summary) else None
        ),
        "latest_measurement": (
            str(summary["end_time"].dropna().max()) if len(summary) else None
        ),
        "max_files_limit": args.max_files,
        "role": "normal-operation baseline and importer verification; not event-response validation",
    }
    with (output_dir / "baseline_manifest.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"Saved {len(summary)} channel summaries: {output_path}")


if __name__ == "__main__":
    main()
