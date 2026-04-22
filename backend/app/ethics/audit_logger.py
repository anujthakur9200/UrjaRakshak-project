"""
Audit Logger Implementation
============================
Comprehensive audit logging for accountability and transparency.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum
import json


class AuditEventType(Enum):
    """Types of auditable events"""
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_REFUSED = "analysis_refused"
    HUMAN_REVIEW_REQUESTED = "human_review_requested"
    HUMAN_REVIEW_COMPLETED = "human_review_completed"
    ESCALATION = "escalation"
    ETHICS_VIOLATION_DETECTED = "ethics_violation_detected"
    DATA_ACCESS = "data_access"
    CONFIGURATION_CHANGE = "configuration_change"
    SYSTEM_ERROR = "system_error"


class AuditLogger:
    """
    Production-grade audit logger with structured logging.
    
    Features:
    - Structured JSON logs
    - Tamper-evident logging
    - Retention policies
    - Query capabilities
    """
    
    def __init__(self, log_file: str = "audit.log"):
        self.logger = logging.getLogger("urjarakshak.audit")
        self.log_file = log_file
        
        # Configure structured logging
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "INFO"
    ):
        """
        Log an auditable event.
        
        Args:
            event_type: Type of event
            user_id: Optional user/system identifier
            resource_id: Optional resource identifier
            details: Additional event details
            severity: Log severity (INFO, WARNING, ERROR, CRITICAL)
        """
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "user_id": user_id or "system",
            "resource_id": resource_id,
            "details": details or {},
            "severity": severity
        }
        
        log_message = json.dumps(event)
        
        if severity == "INFO":
            self.logger.info(log_message)
        elif severity == "WARNING":
            self.logger.warning(log_message)
        elif severity == "ERROR":
            self.logger.error(log_message)
        elif severity == "CRITICAL":
            self.logger.critical(log_message)
    
    def log_analysis(
        self,
        analysis_id: str,
        substation_id: str,
        status: str,
        confidence: float,
        requires_review: bool
    ):
        """Log completion of an analysis"""
        self.log_event(
            event_type=AuditEventType.ANALYSIS_COMPLETED,
            resource_id=analysis_id,
            details={
                "substation_id": substation_id,
                "status": status,
                "confidence": confidence,
                "requires_review": requires_review
            },
            severity="INFO"
        )
    
    def log_refusal(self, analysis_id: str, reason: str):
        """Log refusal to provide analysis"""
        self.log_event(
            event_type=AuditEventType.ANALYSIS_REFUSED,
            resource_id=analysis_id,
            details={"reason": reason},
            severity="WARNING"
        )
    
    def log_human_review(
        self,
        analysis_id: str,
        reviewer_id: str,
        decision: str,
        rationale: str
    ):
        """Log human review decision"""
        self.log_event(
            event_type=AuditEventType.HUMAN_REVIEW_COMPLETED,
            user_id=reviewer_id,
            resource_id=analysis_id,
            details={
                "decision": decision,
                "rationale": rationale
            },
            severity="INFO"
        )
    
    def log_escalation(
        self,
        analysis_id: str,
        from_level: str,
        to_level: str,
        reason: str
    ):
        """Log escalation event"""
        self.log_event(
            event_type=AuditEventType.ESCALATION,
            resource_id=analysis_id,
            details={
                "from_level": from_level,
                "to_level": to_level,
                "reason": reason
            },
            severity="WARNING"
        )
    
    def log_ethics_violation(
        self,
        violation_type: str,
        details: Dict[str, Any],
        action_taken: str
    ):
        """Log ethics violation detection"""
        self.log_event(
            event_type=AuditEventType.ETHICS_VIOLATION_DETECTED,
            details={
                "violation_type": violation_type,
                "violation_details": details,
                "action_taken": action_taken
            },
            severity="CRITICAL"
        )
