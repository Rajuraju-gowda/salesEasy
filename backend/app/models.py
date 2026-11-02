"""Data models and Pydantic schemas for SalesEasy Copilot."""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class IssueCategory(str, Enum):
    OUT_OF_STOCK = "OUT_OF_STOCK"
    INVENTORY_DISCREPANCY = "INVENTORY_DISCREPANCY"
    COMPETITOR_ACTIVITY = "COMPETITOR_ACTIVITY"
    PRODUCT_QUALITY_SAFETY = "PRODUCT_QUALITY_SAFETY"
    PROMPT_INJECTION_SECURITY = "PROMPT_INJECTION_SECURITY"
    GENERAL_FIELD_UPDATE = "GENERAL_FIELD_UPDATE"


class UrgencyLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceModel(BaseModel):
    verified_facts: List[str] = Field(
        default_factory=list,
        description="Grounded facts verified against the official system inventory records.",
    )
    unverified_claims: List[str] = Field(
        default_factory=list,
        description="Subjective or unverified assertions made in the field update.",
    )
    conflicts: List[str] = Field(
        default_factory=list,
        description="Direct contradictions between the field update and verified system data.",
    )


class SalesCopilotAnalysis(BaseModel):
    issue_category: IssueCategory = Field(
        ..., description="Standardized operational category of the field report."
    )
    urgency: UrgencyLevel = Field(
        ..., description="Operational urgency: CRITICAL, HIGH, MEDIUM, LOW."
    )
    evidence: EvidenceModel = Field(
        default_factory=EvidenceModel,
        description="Traceable breakdown of verified facts, unverified claims, and conflicts.",
    )
    recommended_next_action: str = Field(
        ...,
        description="Defensible operational next action (non-commercial, non-medical, bounded).",
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Crucial pieces of missing information needed for final resolution.",
    )
    needs_human_review: bool = Field(
        ...,
        description="Whether a human supervisor/manager must review and authorize the case.",
    )
    review_reason: Optional[str] = Field(
        default=None,
        description="Defensible rationale for why human review is mandatory.",
    )
    model_mode: Optional[str] = Field(
        default="rule_assisted_mock",
        description="Execution mode: live_gemini, rule_assisted_mock, fallback_safety.",
    )
    latency_ms: Optional[float] = Field(
        default=0.0, description="Processing latency in milliseconds."
    )


class AnalyzeRequest(BaseModel):
    field_update: str = Field(
        ...,
        min_length=3,
        max_length=4000,
        description="Plain-text field sales update from rep or retail outlet.",
    )
    outlet_hint: Optional[str] = Field(
        default=None, description="Optional store name hint if provided separately."
    )
    force_mode: Optional[str] = Field(
        default="auto",
        description="Mode override: 'auto', 'mock', 'live', or 'simulate_failure'.",
    )


class InventoryItem(BaseModel):
    outlet: str
    sku: str
    system_stock: int
    unit: str = "units"
    last_verified: str = "2026-11-02 08:00 AM"


class EvaluationResultItem(BaseModel):
    scenario_id: int
    name: str
    input_text: str
    category_match: bool
    urgency_match: bool
    evidence_grounded: bool
    human_review_defensible: bool
    passed: bool
    expected_category: str
    actual_category: str
    expected_urgency: str
    actual_urgency: str
    expected_review: bool
    actual_review: bool
    notes: str
    analysis: SalesCopilotAnalysis

