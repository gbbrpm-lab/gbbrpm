from itertools import combinations

from model import evaluate_gbbrpm
from metrics import summarize


LOCATION_NODES = {
    "N1": ["A", "B", "C", "D", "E"],
    "N2": ["A", "B", "C", "D", "E", "F", "G", "H"],
    "N3": ["A", "B", "C", "D", "E", "F", "G"],
    "N4": ["A", "B", "C", "D", "E", "F"],
    "N5": ["N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10"],
}


INTERMEDIATE_NODES = {
    "N1": ["B", "D", "E"],
    "N2": ["B", "E", "H"],
    "N3": ["C", "E", "G"],
    "N4": ["B", "D", "F"],
    "N5": ["N4", "N12", "N19"],
}


def _row(network, family, param, risk, outlet, **extra):
    row = {
        "network": network,
        "scenario_family": family,
        "parameter": param,
    }

    row.update(summarize(risk, outlet))
    row.update(extra)

    return row


def severity_sweep(
    network,
    nodes,
    edges,
    outlet,
    severities=(0.25, 0.50, 0.75, 1.00),
):
    nz = nodes.loc[nodes.B > 0, "node"].astype(str).tolist()
    source = nz[0] if nz else str(nodes.iloc[0].node)

    rows = []

    for sev in severities:
        n = nodes.copy()
        n.loc[n.node.astype(str) == source, "B"] = sev

        risk, _ = evaluate_gbbrpm(n, edges)

        rows.append(
            _row(
                network,
                "severity",
                sev,
                risk,
                outlet,
                source=source,
            )
        )

    return rows


def lc_stress_sweep(
    network,
    nodes,
    edges,
    outlet,
    scales=(0.50, 0.75, 1.00, 1.25, 1.50),
):
    rows = []

    for scale in scales:
        e = edges.copy()
        e["L"] = e["L"] * scale

        risk, _ = evaluate_gbbrpm(nodes, e)

        rows.append(
            _row(
                network,
                "lc_stress",
                scale,
                risk,
                outlet,
            )
        )

    return rows


def location_sweep(
    network,
    nodes,
    edges,
    outlet,
    severity=0.75,
):
    if network not in LOCATION_NODES:
        raise ValueError(
            f"No historical blockage-location definition for {network}"
        )

    available = set(nodes.node.astype(str))
    rows = []

    for node in LOCATION_NODES[network]:
        if node not in available:
            raise ValueError(
                f"Historical blockage-location node {node} "
                f"not found in {network}"
            )

        n = nodes.copy()

        # Historical location experiment isolates one blockage source.
        n["B"] = 0.0
        n.loc[n.node.astype(str) == node, "B"] = severity

        risk, _ = evaluate_gbbrpm(n, edges)

        rows.append(
            _row(
                network,
                "blockage_location",
                node,
                risk,
                outlet,
                location=node,
                severity=severity,
            )
        )

    return rows


def source_combination_sweep(
    network,
    nodes,
    edges,
    outlet,
):
    sources = (
        nodes.loc[nodes.B > 0, "node"]
        .astype(str)
        .tolist()
    )

    # N10 is a local/intermediate blockage in N5,
    # not one of the three source nodes used in
    # the historical multi-source experiment.
    if network == "N5" and "N10" in sources:
        sources.remove("N10")

    if len(sources) < 2:
        return []

    baseline = {
        str(r.node): float(r.B)
        for r in nodes.itertuples(index=False)
    }

    rows = []

    for k in range(1, len(sources) + 1):
        for combo in combinations(sources, k):
            n = nodes.copy()

            for s in sources:
                n.loc[n.node.astype(str) == s, "B"] = (
                    baseline[s] if s in combo else 0.0
                )

            risk, _ = evaluate_gbbrpm(n, edges)

            rows.append(
                _row(
                    network,
                    "source_combination",
                    "+".join(combo),
                    risk,
                    outlet,
                )
            )

    return rows


def intermediate_blockage_sweep(
    network,
    nodes,
    edges,
    outlet,
    severities=(0.25, 0.50, 0.75),
):
    if network not in INTERMEDIATE_NODES:
        raise ValueError(
            f"No historical intermediate-blockage definition for {network}"
        )

    available = set(nodes.node.astype(str))
    rows = []

    for node in INTERMEDIATE_NODES[network]:
        if node not in available:
            raise ValueError(
                f"Historical intermediate node {node} "
                f"not found in {network}"
            )

        for sev in severities:
            n = nodes.copy()

            # Important:
            # preserve the network's baseline local disturbances
            # and add/replace the selected intermediate blockage.
            n.loc[n.node.astype(str) == node, "B"] = sev

            risk, _ = evaluate_gbbrpm(n, edges)

            rows.append(
                _row(
                    network,
                    "intermediate_blockage",
                    f"{node}:{sev}",
                    risk,
                    outlet,
                    location=node,
                    severity=sev,
                )
            )

    return rows


def run_core_scenarios(
    network,
    nodes,
    edges,
    outlet,
):
    rows = []

    rows += severity_sweep(
        network,
        nodes,
        edges,
        outlet,
    )

    rows += lc_stress_sweep(
        network,
        nodes,
        edges,
        outlet,
    )

    rows += location_sweep(
        network,
        nodes,
        edges,
        outlet,
    )

    if network in ("N3", "N5"):
        rows += source_combination_sweep(
            network,
            nodes,
            edges,
            outlet,
        )

    rows += intermediate_blockage_sweep(
        network,
        nodes,
        edges,
        outlet,
    )

    return rows