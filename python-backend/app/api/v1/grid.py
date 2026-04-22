"""
Grid Topology API — v1
======================
GET /topology      Full node-edge graph for visualisation.
GET /regions       Aggregated region statistics.
GET /substations   Flat list of substations.
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Query

from app.schemas.models import GridEdge, GridNode, GridTopologyResponse, RegionOut, SubstationOut

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Static demo topology (replaced by DB queries in production)
# ─────────────────────────────────────────────────────────────────────

_SUBSTATIONS: list[SubstationOut] = [
    SubstationOut(substation_id="SS-001", name="North Grid Alpha",  region="North", latitude=28.70, longitude=77.10, capacity_mva=150.0, voltage_kv=132.0, status="online"),
    SubstationOut(substation_id="SS-002", name="North Grid Beta",   region="North", latitude=28.72, longitude=77.22, capacity_mva=100.0, voltage_kv=66.0,  status="online"),
    SubstationOut(substation_id="SS-003", name="South Hub Prime",   region="South", latitude=12.97, longitude=77.59, capacity_mva=200.0, voltage_kv=220.0, status="online"),
    SubstationOut(substation_id="SS-004", name="East Industrial",   region="East",  latitude=22.57, longitude=88.36, capacity_mva=120.0, voltage_kv=132.0, status="degraded"),
    SubstationOut(substation_id="SS-005", name="West Rural Feed",   region="West",  latitude=23.02, longitude=72.57, capacity_mva=80.0,  voltage_kv=33.0,  status="online"),
    SubstationOut(substation_id="SS-006", name="Central Dispatch",  region="Central", latitude=23.25, longitude=77.41, capacity_mva=250.0, voltage_kv=400.0, status="online"),
]

_REGIONS: list[RegionOut] = [
    RegionOut(region_id="R-NORTH",   name="North",   num_substations=2, total_capacity_mva=250.0, average_loss_pct=2.8),
    RegionOut(region_id="R-SOUTH",   name="South",   num_substations=1, total_capacity_mva=200.0, average_loss_pct=3.1),
    RegionOut(region_id="R-EAST",    name="East",    num_substations=1, total_capacity_mva=120.0, average_loss_pct=5.4),
    RegionOut(region_id="R-WEST",    name="West",    num_substations=1, total_capacity_mva=80.0,  average_loss_pct=2.2),
    RegionOut(region_id="R-CENTRAL", name="Central", num_substations=1, total_capacity_mva=250.0, average_loss_pct=1.9),
]


def _build_topology() -> GridTopologyResponse:
    nodes: list[GridNode] = []
    edges: list[GridEdge] = []

    # One node per substation
    for ss in _SUBSTATIONS:
        nodes.append(
            GridNode(
                id=ss.substation_id,
                label=ss.name,
                node_type="substation",
                voltage_kv=ss.voltage_kv,
                latitude=ss.latitude,
                longitude=ss.longitude,
                properties={"region": ss.region, "status": ss.status, "capacity_mva": ss.capacity_mva},
            )
        )

        # Two feeder nodes per substation
        for f_idx in range(1, 3):
            feeder_id = f"{ss.substation_id}-F{f_idx:02d}"
            lat_offset = (f_idx - 1.5) * 0.03
            nodes.append(
                GridNode(
                    id=feeder_id,
                    label=f"Feeder {f_idx} ({ss.substation_id})",
                    node_type="feeder",
                    voltage_kv=ss.voltage_kv / 2,
                    latitude=ss.latitude + lat_offset,
                    longitude=ss.longitude + 0.05,
                    properties={"parent": ss.substation_id},
                )
            )
            edges.append(
                GridEdge(
                    id=f"E-{ss.substation_id}-F{f_idx:02d}",
                    source=ss.substation_id,
                    target=feeder_id,
                    edge_type="distribution",
                    length_km=round(2.5 + f_idx * 1.2, 2),
                    resistance_ohm_per_km=0.18,
                    current_a=round(150.0 + f_idx * 20, 1),
                )
            )

    # Inter-substation transmission links
    links = [("SS-001", "SS-002"), ("SS-002", "SS-006"), ("SS-006", "SS-003"), ("SS-006", "SS-004"), ("SS-006", "SS-005")]
    for idx, (src, tgt) in enumerate(links):
        edges.append(
            GridEdge(
                id=f"TX-{idx+1:03d}",
                source=src,
                target=tgt,
                edge_type="transmission",
                length_km=round(15.0 + idx * 8.5, 1),
                resistance_ohm_per_km=0.05,
                current_a=round(400.0 + idx * 30, 1),
            )
        )

    return GridTopologyResponse(
        grid_id="URJA-GRID-V1",
        nodes=nodes,
        edges=edges,
        metadata={
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "regions": [r.name for r in _REGIONS],
        },
    )


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────


@router.get("/topology", response_model=GridTopologyResponse)
async def get_topology(
    region: Optional[str] = Query(None, description="Filter by region name"),
) -> GridTopologyResponse:
    """Return the full grid topology graph (nodes + edges)."""
    topo = _build_topology()
    if region:
        allowed_ss = {ss.substation_id for ss in _SUBSTATIONS if ss.region.lower() == region.lower()}
        topo.nodes = [n for n in topo.nodes if n.id in allowed_ss or n.properties.get("parent") in allowed_ss]
        valid_ids = {n.id for n in topo.nodes}
        topo.edges = [e for e in topo.edges if e.source in valid_ids and e.target in valid_ids]
    return topo


@router.get("/regions", response_model=list[RegionOut])
async def get_regions() -> list[RegionOut]:
    """Return aggregated statistics per region."""
    return _REGIONS


@router.get("/substations", response_model=list[SubstationOut])
async def get_substations(
    region: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> list[SubstationOut]:
    """Return a flat list of substations with optional filters."""
    result = list(_SUBSTATIONS)
    if region:
        result = [s for s in result if s.region.lower() == region.lower()]
    if status:
        result = [s for s in result if s.status.lower() == status.lower()]
    return result
