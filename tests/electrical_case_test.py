from pathlib import Path
import json
import sys
import tempfile
import zipfile

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from electrical_case import (  # noqa: E402
    analyze_event_responses,
    group_status_events,
    summarize_magnitude_archive,
)


CASE_DIR = ROOT / "data" / "electrical" / "socal28_sample"

nodes = pd.read_csv(CASE_DIR / "nodes.csv")
all_edges = pd.read_csv(CASE_DIR / "all_edges.csv")
active_edges = pd.read_csv(CASE_DIR / "active_edges.csv")
mapping = pd.read_csv(CASE_DIR / "meter_mapping.csv")
events = pd.read_csv(CASE_DIR / "status_events.csv")
request_windows = pd.read_csv(CASE_DIR / "event_request_windows.csv")
with (CASE_DIR / "manifest.json").open(encoding="utf-8") as handle:
    manifest = json.load(handle)

assert len(nodes) == 187
assert len(all_edges) == 203
assert len(active_edges) == 177
assert len(mapping) == 226
assert mapping["data_file"].replace("", np.nan).dropna().nunique() == 222
voltage_mapping = mapping.loc[mapping["measurement_kind"] == "voltage_magnitude"]
assert int(voltage_mapping["voltage_response_eligible"].sum()) == 60
assert (
    voltage_mapping["measurement_semantics"]
    == "derived_or_signed_voltage_channel"
).sum() == 6
assert len(events) == 34
assert len(request_windows) == 12
assert {
    "recommended_query_start",
    "recommended_query_end",
}.issubset(request_windows.columns)
assert manifest["snapshot_time"] == "2024-11-14T07:00:00"
assert manifest["dag_in_nominal_orientation"] is True
assert manifest["voltage_response_eligible_mapping_count"] == 60
assert manifest["derived_or_signed_voltage_mapping_count"] == 6

graph = nx.from_pandas_edgelist(
    active_edges, "source", "target", create_using=nx.DiGraph
)
graph.add_nodes_from(nodes["node"])
assert nx.is_directed_acyclic_graph(graph)
assert nx.number_weakly_connected_components(graph) == 10

event_groups = group_status_events(events)
assert len(event_groups) == 12
november_groups = event_groups.loc[
    event_groups["start_time"].astype(str).str.startswith("2024-11-13")
]
assert november_groups["operation_count"].tolist() == [4, 1, 2, 1]

# Exercise the streaming ZIP summarizer without requiring the large archive.
with tempfile.TemporaryDirectory() as temporary:
    archive_path = Path(temporary) / "magnitudes.zip"
    sample = (
        "t,v\n"
        "2024-11-14T07:00:00,100\n"
        "2024-11-14T07:00:01,90\n"
        "2024-11-14T07:00:03,95\n"
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("magnitudes/test_voltage.csv", sample)
        archive.writestr("magnitudes/test_derived.csv", sample)
        # The public archive contains truly zero-byte members, which pandas
        # reports as EmptyDataError rather than a header-only empty frame.
        archive.writestr("magnitudes/test_empty.csv", b"")
        archive.writestr("magnitudes/egauge_22-CT16.csv", sample)
    sample_mapping = pd.DataFrame(
        [
            {
                "data_file": "test_voltage",
                "meter": "meter_1",
                "channel": "L1",
                "measurement_kind": "voltage_magnitude",
                "unit": "V",
                "base_element": "bus_1",
                "nominal_voltage": 100.0,
                "measurement_semantics": "direct_phase_to_ground_voltage_magnitude",
                "voltage_response_eligible": True,
            },
            {
                "data_file": "test_derived",
                "meter": "meter_1",
                "channel": "V_ab",
                "measurement_kind": "voltage_magnitude",
                "unit": "V",
                "base_element": "bus_1",
                "nominal_voltage": 100.0,
                "measurement_semantics": "derived_or_signed_voltage_channel",
                "voltage_response_eligible": False,
            },
            {
                "data_file": "test_empty",
                "meter": "meter_2",
                "channel": "L1",
                "measurement_kind": "voltage_magnitude",
                "unit": "V",
                "base_element": "bus_2",
                "nominal_voltage": 100.0,
                "measurement_semantics": "direct_phase_to_ground_voltage_magnitude",
                "voltage_response_eligible": True,
            },
            {
                "data_file": "egauge_22-C16",
                "meter": "egauge_22",
                "channel": "CT16",
                "measurement_kind": "current_magnitude",
                "unit": "A",
                "base_element": "inv_10",
                "nominal_voltage": np.nan,
                "measurement_semantics": "current_magnitude",
                "voltage_response_eligible": False,
            },
        ]
    )
    summary = summarize_magnitude_archive(archive_path, sample_mapping)
    assert len(summary) == 4
    direct = summary.loc[summary["data_file"] == "test_voltage"].iloc[0]
    derived = summary.loc[summary["data_file"] == "test_derived"].iloc[0]
    empty = summary.loc[summary["data_file"] == "test_empty"].iloc[0]
    aliased = summary.loc[summary["data_file"] == "egauge_22-CT16"].iloc[0]
    assert direct["row_count"] == 3
    assert direct["expected_timestamp_count"] == 4
    assert direct["missing_timestamp_count"] == 1
    assert np.isclose(direct["timestamp_coverage_fraction"], 0.75)
    assert np.isclose(direct["mean"], 95.0)
    assert np.isclose(direct["mean_per_unit"], 0.95)
    assert pd.isna(derived["mean_per_unit"])
    assert derived["per_unit_status"] == "excluded_derived_or_signed_voltage"
    assert empty["data_status"] == "empty"
    assert empty["expected_timestamp_count"] == 0
    assert aliased["measurement_kind"] == "current_magnitude"
    assert aliased["declared_data_file"] == "egauge_22-C16"
    assert aliased["mapping_method"] == "explicit_source_filename_alias"

# Exercise event-window response extraction and the tie-aware top-20% flag.
times = pd.date_range("2024-01-01T00:00:00", periods=181, freq="s")
voltage_values = np.where(times < pd.Timestamp("2024-01-01T00:01:00"), 100.0, 90.0)
power_values = np.where(times < pd.Timestamp("2024-01-01T00:01:00"), 200.0, 150.0)
measurements = {
    "voltage": pd.DataFrame({"t": times, "v": voltage_values}),
    "derived_voltage": pd.DataFrame({"t": times, "v": voltage_values * 10}),
    "power": pd.DataFrame({"t": times, "v": power_values}),
}
response_mapping = pd.DataFrame(
    [
        {
            "data_file": "voltage",
            "meter": "meter_1",
            "channel": "L1",
            "measurement_kind": "voltage_magnitude",
            "base_element": "bus_1",
            "nominal_voltage": 100.0,
            "voltage_response_eligible": True,
        },
        {
            "data_file": "derived_voltage",
            "meter": "meter_1",
            "channel": "V_ab",
            "measurement_kind": "voltage_magnitude",
            "base_element": "bus_1",
            "nominal_voltage": 100.0,
            "voltage_response_eligible": False,
        },
        {
            "data_file": "power",
            "meter": "meter_1",
            "channel": "Mains_Power",
            "measurement_kind": "real_power",
            "base_element": "bus_1",
            "nominal_voltage": np.nan,
        },
    ]
)
response_events = pd.DataFrame(
    [
        {
            "event_time": "2024-01-01T00:01:00",
            "element": "switch_1",
            "previous_status": "NC",
            "new_status": "NO",
            "event_kind": "opening",
        }
    ]
)
coverage, voltage, power, ranking = analyze_event_responses(
    measurements,
    response_mapping,
    response_events,
    before_seconds=30,
    after_seconds=30,
    guard_seconds=1,
)
assert coverage.loc[0, "covered"]
assert coverage.loc[0, "covered_channels"] == 2
assert np.isclose(voltage.loc[0, "absolute_change_per_unit"], 0.10)
assert np.isclose(power.loc[0, "absolute_change"], 50.0)
assert ranking.loc[0, "node"] == "bus_1"
assert ranking.loc[0, "priority_top_20pct"]

print("Electrical-domain preprocessing checks passed.")
