"""
Physics Truth Engine (PTE) - PRODUCTION GRADE
=============================================
This is the CORE of UrjaRakshak - not marketing, real physics.

Validates energy conservation using First Law of Thermodynamics.
Computes technical losses based on electrical engineering principles.
Quantifies uncertainty explicitly.
Refuses to output when confidence is insufficient.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class BalanceStatus(Enum):
    """Energy balance assessment - conservative classification"""
    BALANCED = "balanced"
    MINOR_IMBALANCE = "minor_imbalance"
    SIGNIFICANT_IMBALANCE = "significant_imbalance"
    CRITICAL_IMBALANCE = "critical_imbalance"
    UNCERTAIN = "uncertain"
    REFUSED = "refused"


@dataclass
class ComponentLoss:
    """Individual component loss breakdown"""
    component_id: str
    component_type: str
    rated_power_kva: float
    expected_loss_mwh: float
    loss_percentage: float
    computation_method: str


@dataclass
class PhysicsResult:
    """
    Results from physics validation.
    
    This is what the system actually computes, not fake data.
    """
    # Status
    balance_status: BalanceStatus
    
    # Energy accounting (MWh)
    input_energy_mwh: float
    output_energy_mwh: float
    expected_technical_loss_mwh: float
    actual_loss_mwh: float
    residual_mwh: float
    residual_percentage: float
    
    # Uncertainty quantification
    confidence_score: float  # 0.0 to 1.0
    uncertainty_mwh: float  # ± error band
    measurement_quality: str  # "high", "medium", "low"
    
    # Component breakdown
    component_losses: List[ComponentLoss]
    
    # Metadata
    timestamp: str
    temperature_celsius: float
    refusal_reason: Optional[str] = None
    
    # Physical reasoning
    physical_explanation: str = ""
    
    def should_refuse(self) -> bool:
        """Determine if we should refuse to provide analysis"""
        return self.confidence_score < 0.5 or self.refusal_reason is not None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response"""
        return {
            "status": self.balance_status.value,
            "energy_balance": {
                "input_mwh": round(self.input_energy_mwh, 3),
                "output_mwh": round(self.output_energy_mwh, 3),
                "expected_loss_mwh": round(self.expected_technical_loss_mwh, 3),
                "actual_loss_mwh": round(self.actual_loss_mwh, 3),
                "residual_mwh": round(self.residual_mwh, 3),
                "residual_percentage": round(self.residual_percentage, 2)
            },
            "confidence": {
                "score": round(self.confidence_score, 2),
                "uncertainty_mwh": round(self.uncertainty_mwh, 3),
                "measurement_quality": self.measurement_quality
            },
            "component_losses": [
                {
                    "id": c.component_id,
                    "type": c.component_type,
                    "loss_mwh": round(c.expected_loss_mwh, 3),
                    "loss_percent": round(c.loss_percentage, 2),
                    "method": c.computation_method
                }
                for c in self.component_losses
            ],
            "refusal_reason": self.refusal_reason,
            "physical_explanation": self.physical_explanation
        }


@dataclass
class GridComponent:
    """Grid component with physical properties"""
    component_id: str
    component_type: str  # transformer, line, etc.
    rated_capacity_kva: float
    voltage_kv: Optional[float] = None
    resistance_ohms: Optional[float] = None
    length_km: Optional[float] = None
    efficiency_rating: Optional[float] = None
    age_years: Optional[float] = None
    load_factor: Optional[float] = None  # Current load / rated capacity


class PhysicsEngine:
    """
    Physics Truth Engine - validates energy conservation.
    
    This is REAL engineering, not ML hype.
    Based on:
    - First Law of Thermodynamics
    - Ohm's Law (V = IR)
    - Power loss equations (P = I²R)
    - Transformer physics
    """
    
    # Engineering thresholds (conservative)
    MINOR_THRESHOLD_PERCENT = 2.0
    SIGNIFICANT_THRESHOLD_PERCENT = 5.0
    CRITICAL_THRESHOLD_PERCENT = 10.0
    MIN_CONFIDENCE_SCORE = 0.5
    
    def __init__(
        self,
        temperature_celsius: float = 25.0,
        min_confidence: float = 0.5,
        strict_mode: bool = True
    ):
        """
        Initialize Physics Engine.
        
        Args:
            temperature_celsius: Ambient temperature (affects resistance)
            min_confidence: Minimum confidence for analysis
            strict_mode: If True, refuse low-confidence results
        """
        self.temperature = temperature_celsius
        self.min_confidence = min_confidence
        self.strict_mode = strict_mode
        self.logger = logging.getLogger(f"{__name__}.PhysicsEngine")
        
        self.logger.info(
            f"Physics Engine initialized: "
            f"T={temperature_celsius}°C, "
            f"min_conf={min_confidence}, "
            f"strict={strict_mode}"
        )
    
    def validate_energy_conservation(
        self,
        input_energy_mwh: float,
        output_energy_mwh: float,
        components: List[GridComponent],
        measurement_errors: Optional[Dict[str, float]] = None,
        time_window_hours: float = 24.0
    ) -> PhysicsResult:
        """
        Validate energy conservation for a grid section.
        
        First Law of Thermodynamics:
        Energy_in = Energy_out + Energy_losses
        
        Args:
            input_energy_mwh: Total energy entering section
            output_energy_mwh: Total energy measured at endpoints
            components: List of grid components
            measurement_errors: Known measurement uncertainties
            time_window_hours: Analysis time window
            
        Returns:
            PhysicsResult with detailed analysis
        """
        from datetime import datetime
        
        self.logger.info(
            f"Validating energy conservation: "
            f"In={input_energy_mwh:.2f} MWh, "
            f"Out={output_energy_mwh:.2f} MWh"
        )
        
        # Step 1: Validate inputs
        if input_energy_mwh <= 0:
            return self._create_refused_result(
                "Input energy must be positive",
                input_energy_mwh,
                output_energy_mwh
            )
        
        if output_energy_mwh < 0:
            return self._create_refused_result(
                "Output energy cannot be negative",
                input_energy_mwh,
                output_energy_mwh
            )
        
        if output_energy_mwh > input_energy_mwh * 1.001:
            # 0.1% tolerance for measurement rounding only.
            # Output > input violates First Law of Thermodynamics.
            return self._create_refused_result(
                f"Output ({output_energy_mwh:.3f} MWh) exceeds input ({input_energy_mwh:.3f} MWh) — "
                "violates conservation of energy. Check for meter reversal or data entry error.",
                input_energy_mwh,
                output_energy_mwh
            )
        
        if not components:
            return self._create_refused_result(
                "No components provided - cannot compute technical losses",
                input_energy_mwh,
                output_energy_mwh
            )
        
        # Step 2: Compute expected technical losses
        component_losses, total_expected_loss = self._compute_technical_losses(
            input_energy_mwh=input_energy_mwh,
            components=components,
            time_hours=time_window_hours
        )
        
        # Step 3: Compute actual loss
        actual_loss = input_energy_mwh - output_energy_mwh
        
        # Step 4: Compute residual (unexplained)
        residual = actual_loss - total_expected_loss
        residual_percent = abs(residual) / input_energy_mwh * 100 if input_energy_mwh > 0 else 0
        
        # Step 5: Assess measurement uncertainty
        uncertainty, measurement_quality = self._assess_uncertainty(
            input_energy_mwh=input_energy_mwh,
            measurement_errors=measurement_errors,
            num_components=len(components)
        )
        
        # Step 6: Compute confidence
        confidence = self._compute_confidence(
            residual=residual,
            uncertainty=uncertainty,
            measurement_quality=measurement_quality
        )
        
        # Step 7: Classify balance status
        balance_status = self._classify_balance(
            residual_percent=residual_percent,
            confidence=confidence
        )
        
        # Step 8: Check refusal conditions
        refusal_reason = self._check_refusal(
            confidence=confidence,
            measurement_quality=measurement_quality,
            residual_percent=residual_percent
        )
        
        # Step 9: Generate physical explanation
        explanation = self._generate_explanation(
            input_energy_mwh=input_energy_mwh,
            output_energy_mwh=output_energy_mwh,
            expected_loss=total_expected_loss,
            actual_loss=actual_loss,
            residual=residual,
            confidence=confidence
        )
        
        result = PhysicsResult(
            balance_status=balance_status if not refusal_reason else BalanceStatus.REFUSED,
            input_energy_mwh=input_energy_mwh,
            output_energy_mwh=output_energy_mwh,
            expected_technical_loss_mwh=total_expected_loss,
            actual_loss_mwh=actual_loss,
            residual_mwh=residual,
            residual_percentage=residual_percent,
            confidence_score=confidence,
            uncertainty_mwh=uncertainty,
            measurement_quality=measurement_quality,
            component_losses=component_losses,
            timestamp=datetime.utcnow().isoformat(),
            temperature_celsius=self.temperature,
            refusal_reason=refusal_reason,
            physical_explanation=explanation
        )
        
        self.logger.info(
            f"Analysis complete: Status={balance_status.value}, "
            f"Residual={residual:.2f} MWh ({residual_percent:.2f}%), "
            f"Confidence={confidence:.2f}"
        )
        
        return result
    
    def _compute_technical_losses(
        self,
        input_energy_mwh: float,
        components: List[GridComponent],
        time_hours: float
    ) -> Tuple[List[ComponentLoss], float]:
        """
        Compute expected technical losses based on physics.
        
        Components of technical loss:
        1. I²R losses in transmission/distribution lines
        2. Core losses (no-load) in transformers
        3. Copper losses (load-dependent) in transformers
        4. Corona discharge (HV lines)
        5. Dielectric losses
        """
        component_losses = []
        total_loss = 0.0
        
        for component in components:
            if component.component_type == "transformer":
                loss, method = self._compute_transformer_loss(component, input_energy_mwh)
            elif "line" in component.component_type.lower():
                loss, method = self._compute_line_loss(component, input_energy_mwh)
            else:
                # Generic estimation for unknown components
                loss = input_energy_mwh * 0.01  # 1% default
                method = "generic_estimation"
            
            loss_percent = (loss / input_energy_mwh * 100) if input_energy_mwh > 0 else 0
            
            component_losses.append(ComponentLoss(
                component_id=component.component_id,
                component_type=component.component_type,
                rated_power_kva=component.rated_capacity_kva,
                expected_loss_mwh=loss,
                loss_percentage=loss_percent,
                computation_method=method
            ))
            
            total_loss += loss
        
        return component_losses, total_loss
    
    def _compute_transformer_loss(
        self,
        transformer: GridComponent,
        energy_mwh: float
    ) -> Tuple[float, str]:
        """
        Compute transformer losses (physics-based).
        
        Total loss = Core loss (no-load) + Copper loss (load-dependent)
        
        Core loss: Hysteresis + Eddy current (constant)
        Copper loss: I²R (proportional to load²)
        """
        # No-load loss (typically 0.2-1% of rated capacity)
        if transformer.efficiency_rating:
            no_load_fraction = (1 - transformer.efficiency_rating) * 0.3
        else:
            no_load_fraction = 0.005  # 0.5% default
        
        # Load loss (typically 1-3% at full load)
        if transformer.load_factor:
            load_loss_fraction = 0.01 * (transformer.load_factor ** 2)
        else:
            load_loss_fraction = 0.01  # 1% default
        
        # Aging factor (resistance increases with age)
        aging_multiplier = 1.0
        if transformer.age_years:
            # 1% increase per year (insulation degradation)
            aging_multiplier = 1 + (transformer.age_years / 100)
        
        total_loss = energy_mwh * (no_load_fraction + load_loss_fraction) * aging_multiplier
        
        return total_loss, "transformer_physics_model"
    
    def _compute_line_loss(
        self,
        line: GridComponent,
        energy_mwh: float,
        time_hours: float = 24.0,
    ) -> Tuple[float, str]:
        """
        Compute I²R losses in transmission/distribution lines.

        Correct physics:
          P_avg   = energy_mwh / time_hours           [MW]
          I       = P_avg * 1e6 / (V_LL * sqrt(3))    [A] (3-phase line-to-line)
          P_loss  = I² * R                             [W]
          E_loss  = P_loss * time_hours / 1e6          [MWh]

        Temperature correction on resistance:
          R(T) = R₀ * (1 + α * (T - 20))   α = 0.00393 for copper
        """
        if line.resistance_ohms and line.length_km:
            # Temperature-corrected resistance (copper: α = 0.00393 /°C)
            alpha = 0.00393
            R = line.resistance_ohms * (1 + alpha * (self.temperature - 20))

            if line.voltage_kv and line.voltage_kv > 0:
                # Average power over the time window
                P_avg_mw = energy_mwh / time_hours       # MW
                V_ll_v   = line.voltage_kv * 1e3         # V (line-to-line)
                I_avg    = (P_avg_mw * 1e6) / (V_ll_v * np.sqrt(3))   # Amps
                P_loss_w = (I_avg ** 2) * R              # Watts (I²R)
                loss_mwh = P_loss_w * time_hours / 1e6  # MWh

                # Sanity cap: I²R loss cannot exceed total energy input
                loss_mwh = min(loss_mwh, energy_mwh * 0.40)
            else:
                # Voltage unknown — empirical estimate
                loss_mwh = energy_mwh * 0.025

            method = "i2r_physics_calculation"
        else:
            # No resistance data — empirical estimate by line type
            if "transmission" in line.component_type.lower():
                loss_mwh = energy_mwh * 0.015  # 1.5% typical HV transmission
            else:
                loss_mwh = energy_mwh * 0.030  # 3.0% typical MV distribution
            method = "empirical_line_loss"

        return loss_mwh, method
    
    def _assess_uncertainty(
        self,
        input_energy_mwh: float,
        measurement_errors: Optional[Dict[str, float]],
        num_components: int
    ) -> Tuple[float, str]:
        """Assess total measurement uncertainty"""
        # Base uncertainty from meter accuracy (typically 0.2-2%)
        base_uncertainty_percent = 1.0
        
        if measurement_errors and "meter_class" in measurement_errors:
            base_uncertainty_percent = measurement_errors["meter_class"]
        
        # Uncertainty propagation (more components = more error)
        component_uncertainty = np.sqrt(num_components) * 0.1
        
        total_uncertainty_percent = base_uncertainty_percent + component_uncertainty
        uncertainty_mwh = input_energy_mwh * (total_uncertainty_percent / 100)
        
        # Classify quality
        if total_uncertainty_percent < 1.5:
            quality = "high"
        elif total_uncertainty_percent < 3.0:
            quality = "medium"
        else:
            quality = "low"
        
        return uncertainty_mwh, quality
    
    def _compute_confidence(
        self,
        residual: float,
        uncertainty: float,
        measurement_quality: str
    ) -> float:
        """Compute confidence based on signal-to-noise ratio"""
        if uncertainty == 0:
            uncertainty = 0.001
        
        # Signal-to-noise ratio
        snr = abs(residual) / uncertainty
        
        # Map SNR to confidence
        confidence = min(1.0, snr / 3.0)
        
        # Penalize poor measurement quality
        quality_multiplier = {"high": 1.0, "medium": 0.8, "low": 0.5}
        confidence *= quality_multiplier.get(measurement_quality, 0.5)
        
        return confidence
    
    def _classify_balance(
        self,
        residual_percent: float,
        confidence: float
    ) -> BalanceStatus:
        """Classify energy balance status"""
        if confidence < self.min_confidence:
            return BalanceStatus.UNCERTAIN
        
        if residual_percent < self.MINOR_THRESHOLD_PERCENT:
            return BalanceStatus.BALANCED
        elif residual_percent < self.SIGNIFICANT_THRESHOLD_PERCENT:
            return BalanceStatus.MINOR_IMBALANCE
        elif residual_percent < self.CRITICAL_THRESHOLD_PERCENT:
            return BalanceStatus.SIGNIFICANT_IMBALANCE
        else:
            return BalanceStatus.CRITICAL_IMBALANCE
    
    def _check_refusal(
        self,
        confidence: float,
        measurement_quality: str,
        residual_percent: float
    ) -> Optional[str]:
        """Check if we should refuse to analyze"""
        if not self.strict_mode:
            return None
        
        if confidence < self.min_confidence:
            return (
                f"Confidence ({confidence:.2f}) below minimum threshold "
                f"({self.min_confidence}). Data quality insufficient for reliable analysis."
            )
        
        if measurement_quality == "low" and residual_percent > 3.0:
            return (
                "Measurement quality too low to distinguish technical losses "
                "from anomalies. Recommend meter calibration."
            )
        
        return None
    
    def _generate_explanation(
        self,
        input_energy_mwh: float,
        output_energy_mwh: float,
        expected_loss: float,
        actual_loss: float,
        residual: float,
        confidence: float
    ) -> str:
        """Generate human-readable physical explanation"""
        efficiency = (output_energy_mwh / input_energy_mwh * 100) if input_energy_mwh > 0 else 0
        
        explanation = (
            f"Energy balance analysis: {input_energy_mwh:.2f} MWh input, "
            f"{output_energy_mwh:.2f} MWh output (efficiency: {efficiency:.1f}%). "
            f"Expected technical losses: {expected_loss:.2f} MWh based on component physics. "
            f"Actual losses: {actual_loss:.2f} MWh measured. "
        )
        
        if abs(residual) < 1.0:
            explanation += "Residual within normal operating range."
        elif residual > 0:
            explanation += f"Residual of {residual:.2f} MWh suggests additional losses beyond technical."
        else:
            explanation += f"Negative residual of {residual:.2f} MWh suggests measurement error or unaccounted generation."
        
        explanation += f" Analysis confidence: {confidence:.0%}."
        
        return explanation
    
    def _create_refused_result(
        self,
        reason: str,
        input_energy: float,
        output_energy: float
    ) -> PhysicsResult:
        """Create a refused result"""
        from datetime import datetime
        
        return PhysicsResult(
            balance_status=BalanceStatus.REFUSED,
            input_energy_mwh=input_energy,
            output_energy_mwh=output_energy,
            expected_technical_loss_mwh=0.0,
            actual_loss_mwh=0.0,
            residual_mwh=0.0,
            residual_percentage=0.0,
            confidence_score=0.0,
            uncertainty_mwh=0.0,
            measurement_quality="insufficient",
            component_losses=[],
            timestamp=datetime.utcnow().isoformat(),
            temperature_celsius=self.temperature,
            refusal_reason=reason,
            physical_explanation=f"Analysis refused: {reason}"
        )
