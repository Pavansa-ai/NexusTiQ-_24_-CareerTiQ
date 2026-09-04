"""
Pydantic data models for the Banking Transaction Risk Investigation Assistant.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Channel(str, Enum):
    UPI = "UPI"
    NEFT = "NEFT"
    IMPS = "IMPS"
    RTGS = "RTGS"
    BANK_TRANSFER = "BANK_TRANSFER"
    ATM = "ATM"
    DEBIT_CARD = "DEBIT_CARD"
    CREDIT_CARD = "CREDIT_CARD"
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    NETBANKING = "NETBANKING"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InvestigationStatus(str, Enum):
    ATTENTION_REQUIRED = "ATTENTION_REQUIRED"
    NO_ATTENTION_REQUIRED = "NO_ATTENTION_REQUIRED"


class BaselineConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

class Transaction(BaseModel):
    transaction_id: str
    timestamp: datetime
    description: str = ""
    payee: str = ""
    amount: float
    channel: str = "UNKNOWN"
    row_index: int = -1  # original CSV row for traceability

    model_config = {"frozen": False}


# ---------------------------------------------------------------------------
# Baseline statistics
# ---------------------------------------------------------------------------

class BaselineStats(BaseModel):
    n_historical: int
    confidence: BaselineConfidence
    median_amount: float
    mean_amount: float
    q1: float
    q3: float
    iqr: float
    mad: float
    large_threshold: float   # Q3 + 1.5*IQR
    extreme_threshold: float  # Q3 + 3*IQR
    normal_amount_min: float
    normal_amount_max: float
    common_payees: list[str]
    normal_channels: list[str]
    active_hour_start: int   # inclusive
    active_hour_end: int     # inclusive
    median_daily_txn_count: float
    analysis_period_days: int


# ---------------------------------------------------------------------------
# Risk signals
# ---------------------------------------------------------------------------

class RuleId(str, Enum):
    R1_LARGE_AMOUNT = "R1"
    R2_NEW_PAYEE_BURST = "R2"
    R3_ODD_HOURS = "R3"
    R4_BEHAVIOURAL_DEVIATION = "R4"


class TriggeredRule(BaseModel):
    rule_id: str
    name: str
    severity: str  # MILD | SIGNIFICANT | STRONG | EXTREME
    reason: str
    transaction_ids: list[str] = Field(default_factory=list)
    score_contribution: int = 0


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

class TransactionCluster(BaseModel):
    cluster_id: str
    transaction_ids: list[str]
    rules_triggered: list[str]
    total_amount: float
    time_span_hours: float
    payee: Optional[str] = None
    channel: Optional[str] = None
    explanation: str = ""


# ---------------------------------------------------------------------------
# Pattern deviation breakdown
# ---------------------------------------------------------------------------

class PatternDeviationBreakdown(BaseModel):
    amount_score: float
    time_score: float
    payee_score: float
    channel_score: float
    frequency_score: float
    overall_score: float
    amount_label: str
    time_label: str
    payee_label: str
    channel_label: str
    frequency_label: str


# ---------------------------------------------------------------------------
# Flagged transaction (compact view)
# ---------------------------------------------------------------------------

class FlaggedTransaction(BaseModel):
    transaction_id: str
    timestamp: str
    description: str
    payee: str
    amount: float
    channel: str
    triggered_rules: list[str] = Field(default_factory=list)
    cluster_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Verified evidence object  (sent to Gemini)
# ---------------------------------------------------------------------------

class VerifiedEvidence(BaseModel):
    investigation_status: InvestigationStatus
    priority_score: int
    priority_level: RiskLevel
    baseline_confidence: BaselineConfidence
    triggered_rules: list[TriggeredRule]
    flagged_transactions: list[FlaggedTransaction]
    clusters: list[TransactionCluster]
    baseline: dict[str, Any]
    deviations: dict[str, str]
    customer_name: str = "Unknown"
    analysis_period: str = ""
    total_transactions: int = 0
    evidence_hash: str = ""


# ---------------------------------------------------------------------------
# Gemini AI output
# ---------------------------------------------------------------------------

class GeminiOutput(BaseModel):
    summary: str
    why_attention_required: str
    behavioural_difference: str
    investigator_first_steps: list[str]
    retrieved_documents: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Investigation Report (final)
# ---------------------------------------------------------------------------

class InvestigationReport(BaseModel):
    investigation_status: InvestigationStatus
    priority_score: int
    priority_level: RiskLevel
    baseline_confidence: BaselineConfidence
    customer_name: str
    analysis_period: str
    total_transactions: int
    triggered_rules: list[TriggeredRule]
    flagged_transactions: list[FlaggedTransaction]
    clusters: list[TransactionCluster]
    baseline: dict[str, Any]
    deviations: dict[str, str]
    pattern_deviation: Optional[PatternDeviationBreakdown] = None
    ai_summary: str = ""
    ai_why_attention: str = ""
    ai_behavioural_difference: str = ""
    ai_first_steps: list[str] = Field(default_factory=list)
    ai_grounding_documents: list[str] = Field(default_factory=list)
    ai_available: bool = True
    ai_cached: bool = False
    deterministic_fallback: bool = False
    evidence_hash: str = ""


# ---------------------------------------------------------------------------
# API request / response
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    csv_content: str
    customer_name: str = "Customer"


class AnalyzeResponse(BaseModel):
    success: bool
    report: Optional[InvestigationReport] = None
    error: Optional[str] = None
    validation_warnings: list[str] = Field(default_factory=list)


class SampleCase(str, Enum):
    NORMAL = "normal"
    INVESTIGATION = "investigation"
