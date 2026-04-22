"""
API Models
==========
Pydantic models for request/response validation and serialization.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ComponentType(str, Enum):
    """Grid component types"""
    TRANSFORMER = "transformer"
    TRANSMISSION_LINE = "transmission_line"
    DISTRIBUTION_LINE = "distribution_line"
    SUBSTATION = "substation"
    SWITCH = "switch"


class GridComponentModel(BaseModel):
    """Grid component information"""
    component_id: str = Field(..., description="Unique component identifier")
    component_type: ComponentType = Field(..., description="Type of component")
    rated_capacity_kva: float = Field(..., gt=0, description="Rated capacity in kVA")
    resistance_ohms: Optional[float] = Field(None, ge=0, description="Resistance in ohms")
    efficiency_rating: Optional[float] = Field(None, ge=0, le=1, description="Efficiency (0-1)")
    age_years: Optional[float] = Field(None, ge=0, description="Age in years")
    maintenance_score: Optional[float] = Field(None, ge=0, le=1, description="Maintenance score (0-1)")


class AnalysisRequest(BaseModel):
    """Request for grid section analysis"""
    substation_id: str = Field(..., description="Substation identifier")
    input_energy_mwh: float = Field(..., gt=0, description="Input energy in MWh")
    output_energy_mwh: float = Field(..., ge=0, description="Output energy in MWh")
    components: List[GridComponentModel] = Field(..., min_items=1, description="Grid components")
    measurement_errors: Optional[Dict[str, float]] = Field(None, description="Known measurement errors")
    grid_context: Dict[str, Any] = Field(default_factory=dict, description="Additional grid context")
    historical_patterns: Optional[Dict[str, Any]] = Field(None, description="Historical pattern data")
    time_window_start: Optional[datetime] = Field(None, description="Analysis window start")
    time_window_end: Optional[datetime] = Field(None, description="Analysis window end")
    
    @validator("output_energy_mwh")
    def validate_energy_balance(cls, v, values):
        """Ensure output doesn't exceed input"""
        if "input_energy_mwh" in values and v > values["input_energy_mwh"] * 1.1:
            raise ValueError("Output energy cannot exceed input by more than 10%")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "substation_id": "SS001",
                "input_energy_mwh": 1000.0,
                "output_energy_mwh": 975.0,
                "components": [
                    {
                        "component_id": "TX001",
                        "component_type": "transformer",
                        "rated_capacity_kva": 1000,
                        "efficiency_rating": 0.98,
                        "age_years": 10
                    }
                ],
                "grid_context": {
                    "maintenance_score": 0.85,
                    "days_since_last_calibration": 365
                }
            }
        }


class HypothesisModel(BaseModel):
    """Loss attribution hypothesis"""
    cause: str = Field(..., description="Cause identifier")
    probability: float = Field(..., ge=0, le=1, description="Probability (0-1)")
    confidence: float = Field(..., ge=0, le=1, description="Confidence (0-1)")
    recommended_action: str = Field(..., description="Recommended action")


class AnalysisResponse(BaseModel):
    """Response from grid section analysis"""
    analysis_id: str = Field(..., description="Unique analysis identifier")
    status: str = Field(..., description="Analysis status: completed, refused, error")
    substation_id: Optional[str] = Field(None, description="Substation identifier")
    
    # Physics validation results
    balance_status: Optional[str] = Field(None, description="Energy balance status")
    input_energy_mwh: Optional[float] = Field(None, description="Input energy")
    output_energy_mwh: Optional[float] = Field(None, description="Output energy")
    expected_technical_loss_mwh: Optional[float] = Field(None, description="Expected technical loss")
    actual_loss_mwh: Optional[float] = Field(None, description="Actual measured loss")
    residual_mwh: Optional[float] = Field(None, description="Unexplained residual")
    residual_percentage: Optional[float] = Field(None, description="Residual as percentage")
    confidence_score: Optional[float] = Field(None, description="Overall confidence")
    uncertainty_mwh: Optional[float] = Field(None, description="Measurement uncertainty")
    
    # Attribution results
    primary_causes: Optional[List[str]] = Field(None, description="Primary loss causes")
    secondary_causes: Optional[List[str]] = Field(None, description="Secondary loss causes")
    hypotheses: Optional[List[HypothesisModel]] = Field(None, description="All hypotheses")
    
    # Review and refusal
    requires_human_review: bool = Field(..., description="Requires human review")
    refusal_reason: Optional[str] = Field(None, description="Reason for refusal")
    
    # Metadata
    timestamp: datetime = Field(..., description="Analysis timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "analysis_id": "ANA-20240215123456",
                "status": "completed",
                "substation_id": "SS001",
                "balance_status": "minor_imbalance",
                "residual_mwh": 15.5,
                "residual_percentage": 1.55,
                "confidence_score": 0.85,
                "primary_causes": ["infrastructure_degradation"],
                "requires_human_review": False,
                "timestamp": "2024-02-15T12:34:56Z"
            }
        }


class SyntheticGridRequest(BaseModel):
    """Request for synthetic grid generation"""
    num_substations: int = Field(5, ge=1, le=100, description="Number of substations")
    num_feeders_per_substation: int = Field(10, ge=1, le=50, description="Feeders per substation")
    num_transformers_per_feeder: int = Field(50, ge=1, le=200, description="Transformers per feeder")
    inject_anomaly: bool = Field(False, description="Inject test anomaly")
    anomaly_type: Optional[str] = Field(None, description="Type of anomaly to inject")
    anomaly_severity: float = Field(0.3, ge=0, le=1, description="Anomaly severity (0-1)")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")
    
    class Config:
        json_schema_extra = {
            "example": {
                "num_substations": 5,
                "num_feeders_per_substation": 10,
                "num_transformers_per_feeder": 50,
                "inject_anomaly": True,
                "anomaly_type": "theft",
                "anomaly_severity": 0.3,
                "seed": 42
            }
        }


class SyntheticGridResponse(BaseModel):
    """Response from synthetic grid generation"""
    grid_id: str = Field(..., description="Generated grid identifier")
    num_substations: int = Field(..., description="Number of substations")
    num_feeders: int = Field(..., description="Total feeders")
    num_transformers: int = Field(..., description="Total transformers")
    total_capacity_mva: float = Field(..., description="Total grid capacity in MVA")
    has_anomaly: bool = Field(..., description="Whether anomaly was injected")
    anomaly_type: Optional[str] = Field(None, description="Type of injected anomaly")
    grid_data: Dict[str, Any] = Field(..., description="Full grid topology and data")
    timestamp: datetime = Field(..., description="Generation timestamp")


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Overall status: healthy, degraded, unhealthy")
    components: Dict[str, str] = Field(..., description="Status of each component")
    configuration: Dict[str, Any] = Field(..., description="Active configuration")
    timestamp: datetime = Field(..., description="Check timestamp")


class EthicalCharterResponse(BaseModel):
    """Ethical charter and commitments"""
    version: str
    commitments: List[str]
    principles: List[str]
    data_policies: Dict[str, Any]


class MetricsResponse(BaseModel):
    """System metrics response"""
    analyses_total: int = Field(..., description="Total analyses performed")
    analyses_refused: int = Field(..., description="Analyses refused due to low confidence")
    human_reviews_required: int = Field(..., description="Analyses requiring human review")
    average_confidence: float = Field(..., description="Average confidence score")
    uptime_seconds: int = Field(..., description="System uptime in seconds")
