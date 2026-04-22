"""
Synthetic Grid Generator
========================
Creates reproducible test grids with realistic characteristics.

Purpose:
- Algorithm testing
- Training and education
- Benchmarking
- Reproducible experiments
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import uuid


@dataclass
class Transformer:
    """Distribution transformer model"""
    transformer_id: str
    rated_capacity_kva: float
    voltage_ratio: str  # e.g., "11kV/400V"
    efficiency: float
    age_years: float
    load_factor: float  # Current load / rated capacity
    location: Dict[str, float]  # lat, lon
    
    def compute_losses(self, load_kw: float) -> float:
        """Compute transformer losses at given load"""
        # No-load loss (core loss)
        no_load_loss = self.rated_capacity_kva * 0.002 * (1 - self.efficiency)
        
        # Load loss (copper loss) - proportional to square of load
        load_fraction = load_kw / self.rated_capacity_kva
        load_loss = self.rated_capacity_kva * 0.008 * (load_fraction ** 2)
        
        # Age degradation (1% per year)
        aging_factor = 1 + (self.age_years / 100)
        
        return (no_load_loss + load_loss) * aging_factor


@dataclass
class Feeder:
    """Distribution feeder model"""
    feeder_id: str
    voltage_kv: float
    length_km: float
    conductor_type: str  # "AAC", "ACSR", etc.
    resistance_per_km: float
    transformers: List[Transformer] = field(default_factory=list)
    
    def compute_line_losses(self, current_a: float) -> float:
        """Compute I²R losses in feeder"""
        total_resistance = self.resistance_per_km * self.length_km
        loss_kw = (current_a ** 2) * total_resistance / 1000
        return loss_kw


@dataclass
class Substation:
    """Substation model"""
    substation_id: str
    name: str
    voltage_level_kv: float
    capacity_mva: float
    feeders: List[Feeder] = field(default_factory=list)
    location: Dict[str, float] = field(default_factory=dict)
    
    def total_load(self) -> float:
        """Compute total substation load"""
        total = 0.0
        for feeder in self.feeders:
            for transformer in feeder.transformers:
                total += transformer.rated_capacity_kva * transformer.load_factor
        return total


@dataclass
class SyntheticGrid:
    """Complete synthetic grid model"""
    grid_id: str
    name: str
    substations: List[Substation] = field(default_factory=list)
    generation_timestamp: datetime = field(default_factory=datetime.utcnow)
    has_anomaly: bool = False
    anomaly_description: Optional[str] = None
    
    @property
    def total_capacity_mva(self) -> float:
        """Total grid capacity"""
        return sum(s.capacity_mva for s in self.substations)
    
    @property
    def total_load_mw(self) -> float:
        """Total current load"""
        return sum(s.total_load() for s in self.substations) / 1000
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "grid_id": self.grid_id,
            "name": self.name,
            "substations": [
                {
                    "substation_id": s.substation_id,
                    "name": s.name,
                    "capacity_mva": s.capacity_mva,
                    "num_feeders": len(s.feeders),
                    "total_transformers": sum(len(f.transformers) for f in s.feeders)
                }
                for s in self.substations
            ],
            "total_capacity_mva": self.total_capacity_mva,
            "total_load_mw": self.total_load_mw,
            "has_anomaly": self.has_anomaly
        }


class SyntheticGridGenerator:
    """
    Generates realistic synthetic grid topologies.
    
    Features:
    - Hierarchical structure (substation -> feeder -> transformer)
    - Realistic component parameters
    - Seasonal and daily load variation
    - Infrastructure aging simulation
    - Anomaly injection for testing
    """
    
    def __init__(
        self,
        num_substations: int = 5,
        num_feeders_per_substation: int = 10,
        num_transformers_per_feeder: int = 50,
        seed: Optional[int] = None
    ):
        """
        Initialize synthetic grid generator.
        
        Args:
            num_substations: Number of substations to generate
            num_feeders_per_substation: Feeders per substation
            num_transformers_per_feeder: Transformers per feeder
            seed: Random seed for reproducibility
        """
        self.num_substations = num_substations
        self.num_feeders_per_substation = num_feeders_per_substation
        self.num_transformers_per_feeder = num_transformers_per_feeder
        
        if seed is not None:
            np.random.seed(seed)
        
        self.rng = np.random.RandomState(seed)
    
    def generate(self) -> SyntheticGrid:
        """Generate complete synthetic grid"""
        grid_id = f"GRID-{uuid.uuid4().hex[:8].upper()}"
        
        substations = []
        for i in range(self.num_substations):
            substation = self._generate_substation(i)
            substations.append(substation)
        
        grid = SyntheticGrid(
            grid_id=grid_id,
            name=f"Synthetic Grid {grid_id}",
            substations=substations
        )
        
        return grid
    
    def _generate_substation(self, index: int) -> Substation:
        """Generate a single substation with feeders"""
        substation_id = f"SS{index+1:03d}"
        
        # Random capacity between 20-100 MVA
        capacity_mva = self.rng.uniform(20, 100)
        
        # Generate location (random lat/lon)
        location = {
            "latitude": self.rng.uniform(-90, 90),
            "longitude": self.rng.uniform(-180, 180)
        }
        
        feeders = []
        for j in range(self.num_feeders_per_substation):
            feeder = self._generate_feeder(substation_id, j)
            feeders.append(feeder)
        
        return Substation(
            substation_id=substation_id,
            name=f"Substation {substation_id}",
            voltage_level_kv=33.0,
            capacity_mva=capacity_mva,
            feeders=feeders,
            location=location
        )
    
    def _generate_feeder(self, substation_id: str, index: int) -> Feeder:
        """Generate a single feeder with transformers"""
        feeder_id = f"{substation_id}-F{index+1:02d}"
        
        # Random length between 5-30 km
        length_km = self.rng.uniform(5, 30)
        
        # Typical conductor parameters
        conductor_types = [
            ("AAC", 0.25),
            ("ACSR", 0.20),
            ("AAAC", 0.22)
        ]
        conductor_type, resistance = self.rng.choice(
            [(ct, r) for ct, r in conductor_types],
            p=[0.3, 0.5, 0.2]
        )
        
        transformers = []
        for k in range(self.num_transformers_per_feeder):
            transformer = self._generate_transformer(feeder_id, k, length_km)
            transformers.append(transformer)
        
        return Feeder(
            feeder_id=feeder_id,
            voltage_kv=11.0,
            length_km=length_km,
            conductor_type=conductor_type,
            resistance_per_km=resistance,
            transformers=transformers
        )
    
    def _generate_transformer(
        self, feeder_id: str, index: int, feeder_length: float
    ) -> Transformer:
        """Generate a single distribution transformer"""
        transformer_id = f"{feeder_id}-T{index+1:03d}"
        
        # Capacity distribution: mostly 25-100 kVA
        capacities = [16, 25, 63, 100, 160, 250]
        capacity = self.rng.choice(capacities, p=[0.1, 0.3, 0.3, 0.2, 0.05, 0.05])
        
        # Efficiency: 95-98.5% for modern transformers
        efficiency = self.rng.uniform(0.95, 0.985)
        
        # Age: 0-30 years, weighted toward older
        age = self.rng.exponential(10)
        age = min(age, 40)
        
        # Load factor: typically 0.3-0.8
        load_factor = self.rng.beta(2, 2) * 0.5 + 0.3
        
        # Location along feeder
        location_along_feeder = self.rng.uniform(0, feeder_length)
        location = {
            "latitude": self.rng.uniform(-90, 90),
            "longitude": self.rng.uniform(-180, 180),
            "distance_from_feeder_start_km": location_along_feeder
        }
        
        return Transformer(
            transformer_id=transformer_id,
            rated_capacity_kva=float(capacity),
            voltage_ratio="11kV/400V",
            efficiency=efficiency,
            age_years=age,
            load_factor=load_factor,
            location=location
        )
    
    def inject_anomaly(
        self,
        grid: Optional[SyntheticGrid] = None,
        anomaly_type: str = "theft",
        severity: float = 0.3
    ) -> SyntheticGrid:
        """
        Inject controlled anomalies for testing.
        
        Args:
            grid: Existing grid or generate new one
            anomaly_type: Type of anomaly ("theft", "meter_error", "degradation")
            severity: Severity factor (0.0 to 1.0)
        """
        if grid is None:
            grid = self.generate()
        
        if anomaly_type == "theft":
            # Simulate energy theft by artificially reducing load factors
            # in a subset of transformers
            affected_count = int(len(grid.substations[0].feeders[0].transformers) * severity)
            
            for substation in grid.substations:
                for feeder in substation.feeders[:2]:  # Affect first 2 feeders
                    for transformer in feeder.transformers[:affected_count]:
                        # Reduce apparent load
                        transformer.load_factor *= (1 - severity)
            
            grid.has_anomaly = True
            grid.anomaly_description = f"Energy theft simulation ({severity*100:.0f}% severity)"
        
        elif anomaly_type == "meter_error":
            # Simulate systematic meter error
            for substation in grid.substations[:1]:
                for feeder in substation.feeders:
                    for transformer in feeder.transformers:
                        # Add random error to load factor
                        error = self.rng.uniform(-severity, severity)
                        transformer.load_factor *= (1 + error)
            
            grid.has_anomaly = True
            grid.anomaly_description = f"Meter error simulation (±{severity*100:.0f}%)"
        
        elif anomaly_type == "degradation":
            # Simulate accelerated infrastructure degradation
            for substation in grid.substations:
                for feeder in substation.feeders:
                    for transformer in feeder.transformers:
                        # Artificially age equipment
                        transformer.age_years += 10 * severity
                        # Reduce efficiency
                        transformer.efficiency *= (1 - severity * 0.05)
            
            grid.has_anomaly = True
            grid.anomaly_description = f"Infrastructure degradation ({severity*100:.0f}%)"
        
        return grid
    
    def generate_load_profile(
        self,
        hours: int = 24,
        base_load: float = 100.0,
        peak_factor: float = 1.8
    ) -> np.ndarray:
        """
        Generate realistic daily load profile.
        
        Args:
            hours: Number of hours
            base_load: Base load in kW
            peak_factor: Peak/base ratio
        """
        t = np.linspace(0, 24, hours)
        
        # Typical residential profile: peaks at 10am and 8pm
        morning_peak = np.exp(-((t - 10) ** 2) / 8)
        evening_peak = np.exp(-((t - 20) ** 2) / 8)
        
        profile = base_load * (1 + (peak_factor - 1) * (morning_peak + evening_peak))
        
        # Add random variation
        noise = self.rng.normal(0, base_load * 0.05, hours)
        profile += noise
        
        return np.maximum(profile, base_load * 0.5)  # Minimum 50% load


# Example usage
if __name__ == "__main__":
    generator = SyntheticGridGenerator(
        num_substations=3,
        num_feeders_per_substation=5,
        num_transformers_per_feeder=20,
        seed=42
    )
    
    # Generate clean grid
    grid = generator.generate()
    print(f"\n=== Generated Grid: {grid.grid_id} ===")
    print(f"Substations: {len(grid.substations)}")
    print(f"Total Capacity: {grid.total_capacity_mva:.2f} MVA")
    print(f"Total Load: {grid.total_load_mw:.2f} MW")
    
    # Inject theft anomaly
    grid_with_theft = generator.inject_anomaly(
        anomaly_type="theft",
        severity=0.3
    )
    print(f"\n=== Grid with Anomaly ===")
    print(f"Anomaly: {grid_with_theft.anomaly_description}")
    print(f"New Load: {grid_with_theft.total_load_mw:.2f} MW")
    
    # Generate load profile
    profile = generator.generate_load_profile()
    print(f"\n=== Load Profile ===")
    print(f"Min: {profile.min():.2f} kW")
    print(f"Max: {profile.max():.2f} kW")
    print(f"Avg: {profile.mean():.2f} kW")
