"""Utilities for the SoCal electrical-domain feasibility package."""

from __future__ import annotations

import csv
from collections import Counter
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


TRANSFER_TYPES = (
    "Line",
    "Transformer",
    "Switch",
    "SwitchMultiPosition",
    "CB",
    "Fuse",
    "VFI",
)

CLOSED_STATUS = "NC"
OPEN_STATUS = "NO"

# The frozen topology declares these two data_file values as C16, while the
# public magnitude archive names the corresponding files CT16. Preserve both
# source forms and resolve the mismatch explicitly rather than rewriting either
# source artifact.
MEASUREMENT_FILE_ALIASES = {
    "egauge_22-CT16": "egauge_22-C16",
    "egauge_23-CT16": "egauge_23-C16",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_time(value: str | datetime) -> pd.Timestamp:
    return pd.Timestamp(value)


@dataclass
class TopologySource:
    network: dict
    network_member: str
    status_series: dict[str, list[tuple[pd.Timestamp, str]]]
    source_name: str


def _read_status_csv(raw: bytes) -> list[tuple[pd.Timestamp, str]]:
    rows = []
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    for row in reader:
        rows.append((parse_time(row["t"]), str(row["str"]).strip()))
    rows.sort(key=lambda item: item[0])
    return rows


def load_topology_source(path: Path) -> TopologySource:
    path = path.resolve()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            network_members = sorted(
                name
                for name in archive.namelist()
                if "/network_files/" in name and name.lower().endswith(".json")
            )
            if len(network_members) != 1:
                raise ValueError(
                    "Expected exactly one topology network JSON in the sample archive"
                )
            network_member = network_members[0]
            network = json.loads(archive.read(network_member))
            status_series = {}
            for name in archive.namelist():
                if "/parameter_timeseries/" not in name or not name.endswith(".csv"):
                    continue
                status_series[Path(name).name] = _read_status_csv(archive.read(name))
        return TopologySource(network, network_member, status_series, path.name)

    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as handle:
            return TopologySource(json.load(handle), path.name, {}, path.name)
    raise ValueError("Topology source must be a .zip sample archive or network .json")


def _element_index(network: dict) -> dict[str, tuple[str, dict]]:
    index = {}
    for element_type in TRANSFER_TYPES:
        for element in network.get(element_type, []):
            index[element["name"]] = (element_type, element)
    return index


def _status_reference(element_name: str, port_index: int) -> str:
    suffix = f"-{port_index + 1}" if port_index else ""
    return f"{element_name}{suffix}-tbus_status.csv"


def status_at(
    series: list[tuple[pd.Timestamp, str]],
    snapshot_time: pd.Timestamp,
) -> str | None:
    current = None
    for timestamp, value in series:
        if timestamp > snapshot_time:
            break
        current = value
    return current


def build_topology_tables(
    source: TopologySource,
    snapshot_time: str | datetime,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    snapshot = parse_time(snapshot_time)
    network = source.network
    bus_lookup = {item["name"]: item for item in network.get("Bus", [])}

    nodes = []
    for bus_name, bus in bus_lookup.items():
        nodes.append(
            {
                "node": bus_name,
                "B": 0.0,
                "phases": bus.get("phases", ""),
                "nominal_voltage": bus.get("nominal_voltage", np.nan),
                "groups": "|".join(bus.get("groups", [])),
            }
        )

    edge_rows = []
    for element_type in TRANSFER_TYPES:
        for element in network.get(element_type, []):
            source_bus = element.get("fbus")
            for port_index, target in enumerate(element.get("tbus", [])):
                target_bus = target.get("name")
                if not source_bus or not target_bus:
                    continue

                status = target.get("status", element.get("status"))
                status_file = None
                if isinstance(status, str) and status.startswith("file:"):
                    status_file = status.removeprefix("file:")
                else:
                    candidate = _status_reference(element["name"], port_index)
                    if candidate in source.status_series:
                        status_file = candidate

                if status_file:
                    resolved = status_at(
                        source.status_series.get(status_file, []), snapshot
                    )
                    if resolved is not None:
                        status = resolved

                if status is None:
                    status = target.get("nominal_status", element.get("nominal_status"))

                edge_rows.append(
                    {
                        "source": source_bus,
                        "target": target_bus,
                        "element": element["name"],
                        "element_type": element_type,
                        "port_index": port_index + 1,
                        "phases": element.get("phases", ""),
                        "status": status or "UNSPECIFIED",
                        "nominal_status": target.get(
                            "nominal_status", element.get("nominal_status", "")
                        ),
                        "status_file": status_file or "",
                        "active": status != OPEN_STATUS,
                        "direction_basis": "topology_fbus_to_tbus_unverified_by_measurement",
                        "current_rating": element.get("current_rating", np.nan),
                        "groups": "|".join(element.get("groups", [])),
                    }
                )

    edges = pd.DataFrame(edge_rows)
    active_edges = edges.loc[edges["active"]].copy()

    meter_rows = []
    for meter in network.get("EgaugeMeter", []):
        for register in meter.get("registers", []):
            element_ref = register.get("element", "") or ""
            base_element = element_ref.split(".", 1)[0] if element_ref else ""
            data_file = register.get("data_file", "") or ""
            unit = register.get("unit", "") or ""
            kind = {
                "V": "voltage_magnitude",
                "A": "current_magnitude",
                "W": "real_power",
            }.get(unit, "other")
            nominal_voltage = np.nan
            if base_element in bus_lookup:
                nominal_voltage = bus_lookup[base_element].get(
                    "nominal_voltage", np.nan
                )
            meter_rows.append(
                {
                    "meter": meter.get("name", ""),
                    "channel": register.get("name", ""),
                    "data_file": data_file,
                    "unit": unit,
                    "measurement_kind": kind,
                    "element_reference": element_ref,
                    "base_element": base_element,
                    "nominal_voltage": nominal_voltage,
                    "register_expression": register.get("value", ""),
                    "measurement_semantics": (
                        "direct_phase_to_ground_voltage_magnitude"
                        if unit == "V"
                        and re.search(r"\.(?:ag|bg|cg)$", element_ref)
                        and re.fullmatch(r"L[123]", str(register.get("value", "")))
                        else "unbound_voltage_register"
                        if unit == "V" and (not data_file or not element_ref)
                        else "derived_or_signed_voltage_channel"
                        if unit == "V"
                        else "current_magnitude"
                        if unit == "A"
                        else "real_power"
                        if unit == "W"
                        else "other"
                    ),
                    "voltage_response_eligible": bool(
                        unit == "V"
                        and re.search(r"\.(?:ag|bg|cg)$", element_ref)
                        and re.fullmatch(r"L[123]", str(register.get("value", "")))
                    ),
                    "rating": register.get("I_rating", np.nan),
                    "groups": "|".join(meter.get("groups", [])),
                }
            )

    events = build_status_events(source)
    return pd.DataFrame(nodes), edges, pd.DataFrame(meter_rows), events


def build_status_events(source: TopologySource) -> pd.DataFrame:
    index = _element_index(source.network)
    rows = []
    for filename, series in sorted(source.status_series.items()):
        stem = filename.removesuffix("-tbus_status.csv")
        element_name = stem
        port_index = 1
        if element_name not in index:
            match = re.fullmatch(r"(.+)-(\d+)", stem)
            if not match or match.group(1) not in index:
                continue
            element_name = match.group(1)
            port_index = int(match.group(2))

        element_type, element = index[element_name]
        targets = element.get("tbus", [])
        target = targets[port_index - 1].get("name", "") if len(targets) >= port_index else ""
        previous = None
        for row_index, (timestamp, status) in enumerate(series):
            if row_index == 0:
                previous = status
                continue
            rows.append(
                {
                    "event_time": timestamp.isoformat(),
                    "element": element_name,
                    "element_type": element_type,
                    "port_index": port_index,
                    "source": element.get("fbus", ""),
                    "target": target,
                    "previous_status": previous,
                    "new_status": status,
                    "event_kind": (
                        "opening"
                        if status == OPEN_STATUS
                        else "closing"
                        if status == CLOSED_STATUS
                        else "status_change"
                    ),
                    "status_file": filename,
                }
            )
            previous = status
    columns = [
        "event_time",
        "element",
        "element_type",
        "port_index",
        "source",
        "target",
        "previous_status",
        "new_status",
        "event_kind",
        "status_file",
    ]
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        result = result.sort_values(["event_time", "element", "port_index"])
    return result.reset_index(drop=True)


def topology_diagnostics(
    nodes: pd.DataFrame,
    active_edges: pd.DataFrame,
) -> dict:
    graph = nx.from_pandas_edgelist(
        active_edges, "source", "target", create_using=nx.DiGraph
    )
    edge_nodes = set(graph.nodes)
    all_graph = graph.copy()
    all_graph.add_nodes_from(nodes["node"])
    return {
        "bus_records": int(len(nodes)),
        "active_edge_records": int(len(active_edges)),
        "active_bus_count": int(len(edge_nodes)),
        "isolated_bus_count": int(len(nodes) - len(edge_nodes)),
        "edge_bearing_weak_components": (
            int(nx.number_weakly_connected_components(graph)) if graph else 0
        ),
        "all_bus_weak_components": int(nx.number_weakly_connected_components(all_graph)),
        "dag_in_nominal_orientation": nx.is_directed_acyclic_graph(all_graph),
        "nominal_roots": int(sum(all_graph.in_degree(node) == 0 for node in all_graph)),
        "nominal_sinks": int(sum(all_graph.out_degree(node) == 0 for node in all_graph)),
    }


def _mapping_lookup(mapping: pd.DataFrame) -> dict[str, dict]:
    lookup = {}
    for row in mapping.to_dict("records"):
        data_file = str(row.get("data_file", ""))
        if data_file and data_file not in lookup:
            mapped = dict(row)
            mapped["_declared_data_file"] = data_file
            mapped["_mapping_method"] = "declared_data_file"
            lookup[data_file] = mapped
    for archive_name, declared_name in MEASUREMENT_FILE_ALIASES.items():
        if declared_name in lookup and archive_name not in lookup:
            mapped = dict(lookup[declared_name])
            mapped["_declared_data_file"] = declared_name
            mapped["_mapping_method"] = "explicit_source_filename_alias"
            lookup[archive_name] = mapped
    return lookup


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _voltage_response_eligible(metadata: dict) -> bool:
    """Conservatively accept direct phase-to-ground voltage magnitudes only."""
    if "voltage_response_eligible" in metadata:
        return _as_bool(metadata.get("voltage_response_eligible"))
    channel = str(metadata.get("channel", ""))
    return bool(re.fullmatch(r"L[123]", channel))


def summarize_magnitude_archive(
    archive_path: Path,
    mapping: pd.DataFrame,
    *,
    max_files: int | None = None,
) -> pd.DataFrame:
    lookup = _mapping_lookup(mapping)
    rows = []
    with zipfile.ZipFile(archive_path) as archive:
        members = sorted(
            name
            for name in archive.namelist()
            if name.lower().endswith(".csv") and "/" in name
        )
        if max_files is not None:
            members = members[:max_files]

        for index, member in enumerate(members, start=1):
            values = []
            total_rows = 0
            valid_count = 0
            invalid_timestamp_count = 0
            duplicate_timestamp_count = 0
            out_of_order_timestamp_count = 0
            first_timestamp = None
            last_timestamp = None
            previous_timestamp = None
            positive_delta_seconds: Counter[float] = Counter()
            with archive.open(member) as handle:
                try:
                    chunks = pd.read_csv(handle, chunksize=250_000)
                except pd.errors.EmptyDataError:
                    chunks = ()
                for chunk in chunks:
                    if not {"t", "v"}.issubset(chunk.columns):
                        raise ValueError(f"Expected t,v columns in {member}")
                    total_rows += len(chunk)
                    timestamps = pd.to_datetime(chunk["t"], errors="coerce")
                    invalid_timestamp_count += int(timestamps.isna().sum())
                    valid_timestamps = timestamps.dropna()
                    if not valid_timestamps.empty:
                        current_first = pd.Timestamp(valid_timestamps.iloc[0])
                        current_last = pd.Timestamp(valid_timestamps.iloc[-1])
                        if first_timestamp is None:
                            first_timestamp = current_first
                        if previous_timestamp is not None:
                            boundary_delta = (
                                current_first - previous_timestamp
                            ).total_seconds()
                            if boundary_delta == 0:
                                duplicate_timestamp_count += 1
                            elif boundary_delta < 0:
                                out_of_order_timestamp_count += 1
                            else:
                                positive_delta_seconds[round(boundary_delta, 9)] += 1

                        deltas = (
                            valid_timestamps.diff().dt.total_seconds().iloc[1:]
                        )
                        duplicate_timestamp_count += int((deltas == 0).sum())
                        out_of_order_timestamp_count += int((deltas < 0).sum())
                        positive_counts = deltas.loc[deltas > 0].round(9).value_counts()
                        positive_delta_seconds.update(
                            {
                                float(delta): int(count)
                                for delta, count in positive_counts.items()
                            }
                        )
                        previous_timestamp = current_last
                        last_timestamp = current_last
                    numeric = pd.to_numeric(chunk["v"], errors="coerce").dropna()
                    valid_count += len(numeric)
                    if len(numeric):
                        values.append(numeric.to_numpy(float))

            array = np.concatenate(values) if values else np.array([], dtype=float)
            data_file = Path(member).stem
            metadata = lookup.get(data_file, {})
            nominal = pd.to_numeric(
                pd.Series([metadata.get("nominal_voltage", np.nan)]),
                errors="coerce",
            ).iloc[0]
            mean = float(array.mean()) if len(array) else np.nan
            std = float(array.std(ddof=1)) if len(array) > 1 else 0.0 if len(array) else np.nan
            quantiles = (
                np.quantile(array, [0.05, 0.50, 0.95])
                if len(array)
                else [np.nan, np.nan, np.nan]
            )
            sampling_interval = (
                positive_delta_seconds.most_common(1)[0][0]
                if positive_delta_seconds
                else np.nan
            )
            valid_timestamp_count = total_rows - invalid_timestamp_count
            unique_timestamp_count = max(
                0, valid_timestamp_count - duplicate_timestamp_count
            )
            if (
                first_timestamp is not None
                and last_timestamp is not None
                and pd.notna(sampling_interval)
                and float(sampling_interval) > 0
            ):
                expected_timestamp_count = int(
                    round(
                        (last_timestamp - first_timestamp).total_seconds()
                        / float(sampling_interval)
                    )
                ) + 1
                missing_timestamp_count = max(
                    0, expected_timestamp_count - unique_timestamp_count
                )
                timestamp_coverage_fraction = (
                    unique_timestamp_count / expected_timestamp_count
                    if expected_timestamp_count
                    else np.nan
                )
            else:
                expected_timestamp_count = 0
                missing_timestamp_count = 0
                timestamp_coverage_fraction = np.nan

            measurement_kind = metadata.get("measurement_kind", "unmapped")
            voltage_eligible = (
                measurement_kind == "voltage_magnitude"
                and _voltage_response_eligible(metadata)
            )
            if total_rows == 0:
                per_unit_status = "not_available_empty_channel"
            elif measurement_kind != "voltage_magnitude":
                per_unit_status = "not_applicable"
            elif not voltage_eligible:
                per_unit_status = "excluded_derived_or_signed_voltage"
            elif pd.isna(nominal) or float(nominal) <= 0:
                per_unit_status = "not_available_missing_nominal_voltage"
            else:
                per_unit_status = "available"
            rows.append(
                {
                    "data_file": data_file,
                    "archive_member": member,
                    "declared_data_file": metadata.get("_declared_data_file", ""),
                    "mapping_method": metadata.get("_mapping_method", "unmapped"),
                    "meter": metadata.get("meter", ""),
                    "channel": metadata.get("channel", ""),
                    "measurement_kind": measurement_kind,
                    "measurement_semantics": metadata.get(
                        "measurement_semantics", "unmapped"
                    ),
                    "voltage_response_eligible": voltage_eligible,
                    "unit": metadata.get("unit", ""),
                    "base_element": metadata.get("base_element", ""),
                    "nominal_voltage": nominal,
                    "data_status": "populated" if total_rows else "empty",
                    "start_time": (
                        first_timestamp.isoformat() if first_timestamp is not None else None
                    ),
                    "end_time": (
                        last_timestamp.isoformat() if last_timestamp is not None else None
                    ),
                    "row_count": total_rows,
                    "valid_count": valid_count,
                    "missing_value_count": total_rows - valid_count,
                    "invalid_timestamp_count": invalid_timestamp_count,
                    "duplicate_timestamp_count": duplicate_timestamp_count,
                    "out_of_order_timestamp_count": out_of_order_timestamp_count,
                    "sampling_interval_seconds": sampling_interval,
                    "expected_timestamp_count": expected_timestamp_count,
                    "missing_timestamp_count": missing_timestamp_count,
                    "timestamp_coverage_fraction": timestamp_coverage_fraction,
                    "minimum": float(array.min()) if len(array) else np.nan,
                    "p05": float(quantiles[0]),
                    "mean": mean,
                    "median": float(quantiles[1]),
                    "p95": float(quantiles[2]),
                    "maximum": float(array.max()) if len(array) else np.nan,
                    "standard_deviation": std,
                    "per_unit_status": per_unit_status,
                    "mean_per_unit": (
                        mean / float(nominal)
                        if per_unit_status == "available" and pd.notna(mean)
                        else np.nan
                    ),
                }
            )
            if index % 10 == 0 or index == len(members):
                print(f"Summarized {index}/{len(members)} magnitude files")
    return pd.DataFrame(rows)


def load_measurement_sources(paths: list[Path]) -> dict[str, pd.DataFrame]:
    frames: dict[str, list[pd.DataFrame]] = {}
    for path in paths:
        if path.is_dir():
            files = sorted(path.rglob("*.csv"))
            for file in files:
                frame = pd.read_csv(file)
                if {"t", "v"}.issubset(frame.columns):
                    frames.setdefault(file.stem, []).append(frame)
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in sorted(archive.namelist()):
                    if not member.lower().endswith(".csv"):
                        continue
                    with archive.open(member) as handle:
                        frame = pd.read_csv(handle)
                    if {"t", "v"}.issubset(frame.columns):
                        frames.setdefault(Path(member).stem, []).append(frame)
        else:
            raise ValueError(f"Measurement source must be a directory or ZIP: {path}")

    combined = {}
    for data_file, parts in frames.items():
        frame = pd.concat(parts, ignore_index=True)
        frame["t"] = pd.to_datetime(frame["t"], errors="coerce")
        frame["v"] = pd.to_numeric(frame["v"], errors="coerce")
        frame = frame.dropna(subset=["t"]).sort_values("t").drop_duplicates("t")
        combined[data_file] = frame.reset_index(drop=True)
    return combined


def group_status_events(events: pd.DataFrame, gap_seconds: int = 60) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    working = events.copy()
    working["event_time"] = pd.to_datetime(working["event_time"])
    working = working.sort_values("event_time")
    groups = []
    current = []
    last_time = None
    for row in working.to_dict("records"):
        timestamp = pd.Timestamp(row["event_time"])
        if last_time is not None and (timestamp - last_time).total_seconds() > gap_seconds:
            groups.append(current)
            current = []
        current.append(row)
        last_time = timestamp
    if current:
        groups.append(current)

    result = []
    for index, group in enumerate(groups, start=1):
        start = min(pd.Timestamp(row["event_time"]) for row in group)
        end = max(pd.Timestamp(row["event_time"]) for row in group)
        result.append(
            {
                "event_group": f"E{index:02d}_{start.strftime('%Y%m%dT%H%M%S')}",
                "start_time": start,
                "end_time": end,
                "operation_count": len(group),
                "operations": "|".join(
                    f"{row['element']}:{row['previous_status']}->{row['new_status']}"
                    for row in group
                ),
                "event_kinds": "|".join(sorted({row["event_kind"] for row in group})),
            }
        )
    return pd.DataFrame(result)


def analyze_event_responses(
    measurements: dict[str, pd.DataFrame],
    mapping: pd.DataFrame,
    events: pd.DataFrame,
    *,
    before_seconds: int = 60,
    after_seconds: int = 60,
    guard_seconds: int = 5,
    group_gap_seconds: int = 60,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_groups = group_status_events(events, group_gap_seconds)
    lookup = _mapping_lookup(mapping)
    voltage_rows = []
    power_rows = []
    coverage_rows = []

    for event in event_groups.to_dict("records"):
        start = pd.Timestamp(event["start_time"])
        end = pd.Timestamp(event["end_time"])
        before_start = start - pd.Timedelta(seconds=before_seconds + guard_seconds)
        before_end = start - pd.Timedelta(seconds=guard_seconds)
        after_start = end + pd.Timedelta(seconds=guard_seconds)
        after_end = after_start + pd.Timedelta(seconds=after_seconds)
        covered_channels = 0

        for data_file, frame in measurements.items():
            metadata = lookup.get(data_file)
            if not metadata or metadata.get("measurement_kind") not in {
                "voltage_magnitude",
                "real_power",
            }:
                continue
            if (
                metadata.get("measurement_kind") == "voltage_magnitude"
                and not _voltage_response_eligible(metadata)
            ):
                continue
            before = frame.loc[
                (frame["t"] >= before_start) & (frame["t"] < before_end), "v"
            ].dropna()
            after = frame.loc[
                (frame["t"] >= after_start) & (frame["t"] < after_end), "v"
            ].dropna()
            if before.empty or after.empty:
                continue
            covered_channels += 1
            before_median = float(before.median())
            after_median = float(after.median())
            absolute_change = abs(after_median - before_median)
            relative_change = absolute_change / max(abs(before_median), 1e-12)
            row = {
                "event_group": event["event_group"],
                "event_start": start.isoformat(),
                "event_end": end.isoformat(),
                "operations": event["operations"],
                "data_file": data_file,
                "declared_data_file": metadata.get("_declared_data_file", ""),
                "mapping_method": metadata.get("_mapping_method", "unmapped"),
                "meter": metadata.get("meter", ""),
                "channel": metadata.get("channel", ""),
                "base_element": metadata.get("base_element", ""),
                "before_count": len(before),
                "after_count": len(after),
                "before_median": before_median,
                "after_median": after_median,
                "absolute_change": absolute_change,
                "relative_change": relative_change,
            }
            if metadata["measurement_kind"] == "voltage_magnitude":
                nominal = pd.to_numeric(
                    pd.Series([metadata.get("nominal_voltage", np.nan)]),
                    errors="coerce",
                ).iloc[0]
                row["nominal_voltage"] = nominal
                row["absolute_change_per_unit"] = (
                    absolute_change / float(nominal)
                    if pd.notna(nominal) and float(nominal) > 0
                    else np.nan
                )
                row["deviation_increase_per_unit"] = (
                    max(
                        0.0,
                        abs(after_median / float(nominal) - 1.0)
                        - abs(before_median / float(nominal) - 1.0),
                    )
                    if pd.notna(nominal) and float(nominal) > 0
                    else np.nan
                )
                voltage_rows.append(row)
            else:
                power_rows.append(row)

        coverage_rows.append(
            {
                **event,
                "before_window_start": before_start.isoformat(),
                "before_window_end": before_end.isoformat(),
                "after_window_start": after_start.isoformat(),
                "after_window_end": after_end.isoformat(),
                "covered_channels": covered_channels,
                "covered": covered_channels > 0,
            }
        )

    voltage = pd.DataFrame(voltage_rows)
    power = pd.DataFrame(power_rows)
    coverage = pd.DataFrame(coverage_rows)
    ranking_rows = []
    if not voltage.empty:
        grouped = (
            voltage.groupby(["event_group", "base_element"], as_index=False)
            .agg(
                observed_response=("absolute_change_per_unit", "max"),
                phase_channels=("data_file", "count"),
            )
        )
        for event_group, event_rows in grouped.groupby("event_group"):
            event_rows = event_rows.sort_values(
                ["observed_response", "base_element"], ascending=[False, True]
            ).reset_index(drop=True)
            nominal_k = max(1, math.ceil(0.20 * len(event_rows)))
            cutoff = float(event_rows.loc[nominal_k - 1, "observed_response"])
            for rank, row in enumerate(event_rows.itertuples(index=False), start=1):
                ranking_rows.append(
                    {
                        "event_group": event_group,
                        "rank": rank,
                        "node": row.base_element,
                        "observed_response": row.observed_response,
                        "phase_channels": row.phase_channels,
                        "priority_k_nominal": nominal_k,
                        "priority_cutoff": cutoff,
                        "priority_top_20pct": (
                            row.observed_response > 0
                            and row.observed_response >= cutoff
                        ),
                    }
                )
    ranking = pd.DataFrame(ranking_rows)
    return coverage, voltage, power, ranking
