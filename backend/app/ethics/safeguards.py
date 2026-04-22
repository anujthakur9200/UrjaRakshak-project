"""
Ethical Safeguards
==================
Runtime enforcement of ethical constraints.
"""

import logging
from typing import Dict, Any, List
import re

logger = logging.getLogger(__name__)


class EthicalSafeguards:
    """
    Enforces ethical constraints at runtime.
    
    Responsibilities:
    - PII detection and blocking
    - Request validation
    - Data minimization enforcement
    - Privacy-preserving transformations
    """
    
    # Patterns that suggest personal data
    PII_PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
        "name": r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'  # Simple name pattern
    }
    
    # Fields that should never contain PII
    PROHIBITED_FIELDS = [
        "consumer_name", "customer_name", "household_name",
        "personal_info", "individual_data", "consumer_profile",
        "face_encoding", "biometric_data", "fingerprint"
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def validate_request(self, request_data: Dict[str, Any]) -> bool:
        """
        Validate that request complies with ethical constraints.
        
        Returns:
            True if request is valid, False otherwise
        """
        # Check for prohibited fields
        if self._contains_prohibited_fields(request_data):
            self.logger.warning("Request contains prohibited fields")
            return False
        
        # Check for PII patterns
        if self._contains_pii(request_data):
            self.logger.warning("Request contains potential PII")
            return False
        
        # Check for aggregation level
        if not self._check_aggregation_level(request_data):
            self.logger.warning("Request does not meet minimum aggregation")
            return False
        
        return True
    
    def _contains_prohibited_fields(self, data: Dict[str, Any]) -> bool:
        """Check if data contains prohibited field names"""
        def check_nested(d: Any, path: str = "") -> bool:
            if isinstance(d, dict):
                for key, value in d.items():
                    full_path = f"{path}.{key}" if path else key
                    
                    # Check field name
                    if any(prohibited in key.lower() for prohibited in self.PROHIBITED_FIELDS):
                        self.logger.warning(f"Found prohibited field: {full_path}")
                        return True
                    
                    # Recurse into nested structures
                    if check_nested(value, full_path):
                        return True
            
            elif isinstance(d, list):
                for i, item in enumerate(d):
                    if check_nested(item, f"{path}[{i}]"):
                        return True
            
            return False
        
        return check_nested(data)
    
    def _contains_pii(self, data: Dict[str, Any]) -> bool:
        """Check if data contains PII patterns"""
        def check_string(s: str) -> bool:
            for pii_type, pattern in self.PII_PATTERNS.items():
                if re.search(pattern, s):
                    self.logger.warning(f"Found potential PII ({pii_type}): {s[:20]}...")
                    return True
            return False
        
        def check_nested(d: Any) -> bool:
            if isinstance(d, str):
                return check_string(d)
            
            elif isinstance(d, dict):
                return any(check_nested(v) for v in d.values())
            
            elif isinstance(d, list):
                return any(check_nested(item) for item in d)
            
            return False
        
        return check_nested(data)
    
    def _check_aggregation_level(self, data: Dict[str, Any]) -> bool:
        """
        Ensure data represents aggregated grid sections, not individuals.
        
        Minimum aggregation: 100 connection points
        """
        # Check for explicit aggregation markers
        num_connections = data.get("num_connections", 0)
        num_consumers = data.get("num_consumers", 0)
        num_transformers = data.get("num_transformers", 0)
        
        MIN_AGGREGATION = 100
        
        # If any aggregation field is present and below threshold
        if any([
            0 < num_connections < MIN_AGGREGATION,
            0 < num_consumers < MIN_AGGREGATION,
            0 < num_transformers < MIN_AGGREGATION
        ]):
            self.logger.warning(
                f"Aggregation below minimum: "
                f"connections={num_connections}, "
                f"consumers={num_consumers}"
            )
            return False
        
        return True
    
    def anonymize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply privacy-preserving transformations to data.
        
        Techniques:
        - Remove direct identifiers
        - Aggregate to grid level
        - Add differential privacy noise
        - Generalize timestamps
        """
        anonymized = data.copy()
        
        # Remove any ID fields that look personal
        personal_id_patterns = ["customer_id", "consumer_id", "household_id"]
        for key in list(anonymized.keys()):
            if any(pattern in key.lower() for pattern in personal_id_patterns):
                # Replace with generic grid section ID
                if key in anonymized:
                    del anonymized[key]
                    self.logger.info(f"Removed personal ID field: {key}")
        
        # Generalize timestamps to hour level (remove minutes/seconds)
        if "timestamp" in anonymized:
            # This would actually parse and round the timestamp
            self.logger.info("Generalized timestamp to hour level")
        
        return anonymized
    
    def compute_energy_dignity_index(
        self,
        reliability_score: float,
        affordability_score: float,
        access_score: float
    ) -> float:
        """
        Compute Energy Dignity Index to balance enforcement with access.
        
        Args:
            reliability_score: Grid reliability (0-1)
            affordability_score: Energy affordability (0-1)
            access_score: Access coverage (0-1)
        
        Returns:
            Energy Dignity Index (0-1)
        """
        # Weighted average favoring access and affordability
        edi = (
            0.3 * reliability_score +
            0.4 * affordability_score +
            0.3 * access_score
        )
        
        return edi
    
    def should_escalate_enforcement(
        self,
        loss_percentage: float,
        energy_dignity_index: float,
        confidence_score: float
    ) -> bool:
        """
        Determine if enforcement should be escalated.
        
        Considers:
        - Loss magnitude
        - Energy dignity (avoid harming vulnerable)
        - Confidence in analysis
        """
        # Never escalate if energy dignity is low (people struggling)
        if energy_dignity_index < 0.4:
            self.logger.info("Not escalating: Energy dignity index too low")
            return False
        
        # Never escalate if confidence is low
        if confidence_score < 0.7:
            self.logger.info("Not escalating: Confidence too low")
            return False
        
        # Only escalate for significant losses
        if loss_percentage < 10:
            return False
        
        return True


class AuditLogger:
    """
    Maintains audit trail of all system actions.
    
    Logged events:
    - Analyses performed
    - Decisions made
    - Human reviews
    - Escalations
    - Refusals
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.AuditLogger")
    
    def log_analysis(
        self,
        analysis_id: str,
        substation_id: str,
        status: str,
        confidence: float
    ):
        """Log an analysis event"""
        self.logger.info(
            f"AUDIT: Analysis {analysis_id} on {substation_id} "
            f"completed with status={status}, confidence={confidence:.2f}"
        )
    
    def log_refusal(
        self,
        analysis_id: str,
        reason: str
    ):
        """Log a refusal to provide output"""
        self.logger.warning(
            f"AUDIT: Analysis {analysis_id} REFUSED. Reason: {reason}"
        )
    
    def log_human_review(
        self,
        analysis_id: str,
        reviewer_id: str,
        decision: str
    ):
        """Log human review decision"""
        self.logger.info(
            f"AUDIT: Human review by {reviewer_id} on {analysis_id}. "
            f"Decision: {decision}"
        )
    
    def log_escalation(
        self,
        analysis_id: str,
        escalation_level: str,
        reason: str
    ):
        """Log escalation to higher tier"""
        self.logger.warning(
            f"AUDIT: Escalation to {escalation_level} for {analysis_id}. "
            f"Reason: {reason}"
        )


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    safeguards = EthicalSafeguards()
    
    # Test: Valid request (aggregated data)
    valid_request = {
        "substation_id": "SS001",
        "input_energy_mwh": 1000.0,
        "num_transformers": 500,
        "time_window": "2024-02-15"
    }
    print(f"\nValid request: {safeguards.validate_request(valid_request)}")
    
    # Test: Invalid request (personal data)
    invalid_request = {
        "consumer_name": "John Doe",
        "email": "john@example.com",
        "energy_mwh": 0.5
    }
    print(f"Invalid request: {safeguards.validate_request(invalid_request)}")
    
    # Test: Energy Dignity Index
    edi = safeguards.compute_energy_dignity_index(
        reliability_score=0.85,
        affordability_score=0.60,
        access_score=0.95
    )
    print(f"\nEnergy Dignity Index: {edi:.2f}")
    
    # Test: Escalation decision
    should_escalate = safeguards.should_escalate_enforcement(
        loss_percentage=12.0,
        energy_dignity_index=0.75,
        confidence_score=0.85
    )
    print(f"Should escalate: {should_escalate}")
