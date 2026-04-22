"""
Pydantic schemas for python-backend API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────


class ComponentTypeEnum(str, Enum):
    TRANSFORMER = "transformer"
    TRANSMISSION_LINE = "transmission_line"
    DISTRIBUTION = "distribution"
    SUBSTATION = "substation"


class BalanceStatusEnum(str, Enum):
    BALANCED = "balanced"
    MINOR_IMBALANCE = "minor_imbalance"
    SIGNIFICANT_IMBALANCE = "significant_imbalance"
    CRITICAL_IMBALANCE = "critical_imbalance"
    UNCERTAIN = "uncertain"


# ─────────────────────────────────────────────────────────────────────
# Component schemas
# ─────────────────────────────────────────────────────────────────────


class ComponentInput(BaseModel):
    component_id: str = Field(..., description="Unique component identifier")
    component_type: str = Field(..., description="transformer | transmission_line | distribution")
    rated_kva: Optional[float] = Field(None, gt=0, description="Rated capacity (kVA) — transformers")
    load_factor: Optional[float] = Field(None, ge=0.0, le=1.0, description="Load factor 0–1")
    efficiency: Optional[float] = Field(None, ge=0.5, le=1.0, description="Efficiency 0–1")
    age_years: Optional[float] = Field(None, ge=0.0, description="Age in years")
    current_a: Optional[float] = Field(None, ge=0.0, description="Current (A) — lines")
    resistance_ohm_per_km: Optional[float] = Field(None, ge=0.0, description="Resistance Ω/km")
    length_km: Optional[float] = Field(None, ge=0.0, description="Line length (km)")
    voltage_kv: Optional[float] = Field(None, gt=0.0, description="Voltage (kV)")


class ComponentLossOut(BaseModel):
    component_id: str
    component_type: str
    calculated_loss_kwh: float
    loss_percentage: float
    confidence: float


# ─────────────────────────────────────────────────────────────────────
# Analysis request / response
# ─────────────────────────────────────────────────────────────────────


class AnalysisRequest(BaseModel):
    substation_id: str = Field(..., description="Substation identifier")
    input_kwh: float = Field(..., gt=0, description="Input energy (kWh)")
    output_kwh: float = Field(..., ge=0, description="Output energy (kWh)")
    components: List[ComponentInput] = Field(..., min_length=1)

    @field_validator("output_kwh")
    @classmethod
    def output_below_input(cls, v: float, info) -> float:
        input_kwh = info.data.get("input_kwh")
        if input_kwh is not None and v > input_kwh * 1.05:
            raise ValueError("output_kwh cannot exceed input_kwh by more than 5 %")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "substation_id": "SS-001",
                "input_kwh": 10000.0,
                "output_kwh": 9700.0,
                "components": [
                    {
                        "component_id": "TX-001",
                        "component_type": "transformer",
                        "rated_kva": 500,
                        "load_factor": 0.75,
                        "efficiency": 0.97,
                        "age_years": 8,
                    }
                ],
            }
        }
    }


class HypothesisOut(BaseModel):
    cause: str
    probability: float
    confidence: float
    description: str
    recommended_action: str


class AnalysisResponse(BaseModel):
    analysis_id: str
    substation_id: str
    status: str
    total_input_kwh: float
    total_output_kwh: float
    total_loss_kwh: float
    loss_percentage: float
    technical_loss_kwh: float
    residual_kwh: float
    residual_pct: float
    balance_status: str
    confidence_score: float
    components: List[ComponentLossOut]
    hypotheses: List[HypothesisOut]
    timestamp: datetime


class AnalysisHistoryItem(BaseModel):
    analysis_id: str
    substation_id: str
    balance_status: str
    loss_percentage: float
    confidence_score: float
    timestamp: datetime


# ─────────────────────────────────────────────────────────────────────
# Grid topology schemas
# ─────────────────────────────────────────────────────────────────────


class GridNode(BaseModel):
    id: str
    label: str
    node_type: str          # substation | transformer | feeder | consumer
    voltage_kv: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class GridEdge(BaseModel):
    id: str
    source: str
    target: str
    edge_type: str          # transmission | distribution | feeder
    length_km: Optional[float] = None
    resistance_ohm_per_km: Optional[float] = None
    current_a: Optional[float] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class GridTopologyResponse(BaseModel):
    grid_id: str
    nodes: List[GridNode]
    edges: List[GridEdge]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubstationOut(BaseModel):
    substation_id: str
    name: str
    region: str
    latitude: float
    longitude: float
    capacity_mva: float
    voltage_kv: float
    status: str


class RegionOut(BaseModel):
    region_id: str
    name: str
    num_substations: int
    total_capacity_mva: float
    average_loss_pct: float


# ─────────────────────────────────────────────────────────────────────
# Streaming / meter event schemas
# ─────────────────────────────────────────────────────────────────────


class MeterEvent(BaseModel):
    event_id: str = Field(..., description="Unique event ID")
    substation_id: str
    meter_id: str
    timestamp: datetime
    energy_kwh: float
    voltage_v: float
    current_a: float
    power_factor: float = Field(..., ge=-1.0, le=1.0)
    event_type: str = Field("reading", description="reading | alarm | outage")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    received: bool
    event_id: str
    message: str


# ─────────────────────────────────────────────────────────────────────
# AI schemas
# ─────────────────────────────────────────────────────────────────────


class AIInterpretRequest(BaseModel):
    analysis_id: str
    language: str = Field("en", description="Response language code")
    detail_level: str = Field("standard", description="brief | standard | detailed")


class AIInterpretResponse(BaseModel):
    analysis_id: str
    summary: str
    key_findings: List[str]
    recommended_actions: List[str]
    risk_level: str
    generated_at: datetime
    model_used: str


class GHIDashboardResponse(BaseModel):
    ghi_score: float = Field(..., ge=0.0, le=100.0)
    risk_level: str
    components: Dict[str, float]
    trend: str
    last_updated: datetime


class AIStatusResponse(BaseModel):
    available: bool
    provider: Optional[str]
    model: Optional[str]
    message: str


# ─────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    database: Dict[str, Any]
