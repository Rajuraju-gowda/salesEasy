"""Safety guardrails, prompt injection detection, and post-generation sanitization for SalesEasy."""
import re
from typing import Tuple, List, Dict, Any
from app.models import (
    SalesCopilotAnalysis,
    IssueCategory,
    UrgencyLevel,
    EvidenceModel,
)


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"disregard\s+(all\s+)?(previous\s+)?prompts?",
    r"system\s+(override|bypass)",
    r"mark\s+(this\s+)?resolved(\s+with\s+low\s+urgency)?",
    r"set\s+urgency\s+to\s+low",
    r"you\s+are\s+now\s+(an\s+admin|in\s+developer\s+mode|unrestricted)",
    r"bypass\s+safety",
    r"authorize\s+(immediate\s+)?(discount|price\s+match|credit)",
    r"do\s+not\s+flag",
    r"do\s+not\s+escalate",
]


COMMERCIAL_ACTION_PATTERNS = [
    r"price\s+match(\s+approved|\s+granted)?",
    r"immediate\s+discount",
    r"credit\s+note\s+authorized",
    r"commercial\s+override",
]


MEDICAL_DIAGNOSIS_PATTERNS = [
    r"diagnos(is|ed|ing)",
    r"food\s+poisoning",
    r"gastroenteritis",
    r"allergic\s+reaction",
    r"prescrib(e|ing|tion)",
    r"take\s+(medicine|antibiotics)",
]


def detect_prompt_injection(text: str) -> Tuple[bool, str]:
    """
    Check if the incoming field text contains prompt injection or adversarial attempts.
    Returns (is_injected, matched_reason).
    """
    normalized = text.lower().strip()
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, normalized)
        if match:
            return True, f"Detected adversarial pattern: '{match.group(0)}'"
    return False, ""


def check_for_fabricated_numbers(text: str, analysis: SalesCopilotAnalysis) -> SalesCopilotAnalysis:
    """
    Ensure the copilot never invents lost sales numbers or financial impact figures
    when the field rep did not provide verified figures.
    """
    # Check if text claims 'major lost sales' without specific numbers
    if "lost sales" in text.lower() or "huge loss" in text.lower() or "major loss" in text.lower():
        # Check if the rep text had numbers
        numbers_in_input = re.findall(r"\b\d+[\d,]*\b", text)
        
        # Check if recommendation or evidence has numbers not present in input or verified stock
        rec = analysis.recommended_next_action
        action_numbers = re.findall(r"(?:₹|\$|usd|rs\.?|units?)\s*(\d+[\d,]*)", rec, re.IGNORECASE)
        
        if not numbers_in_input and action_numbers:
            # Strip fabricated monetary/unit estimates from action
            analysis.recommended_next_action = (
                "Initiate standard replenishment order for verified stockout. "
                "Request store POS transaction logs to quantify reported lost sales; do not estimate figures."
            )
        
        # Ensure unverified claim specifically warns against fabricated figures
        has_lost_sales_claim = any("lost sales" in claim.lower() for claim in analysis.evidence.unverified_claims)
        if not has_lost_sales_claim:
            analysis.evidence.unverified_claims.append(
                "Rep claims major lost sales; no quantifiable transaction records or revenue figures provided."
            )

    return analysis


def sanitize_commercial_and_medical_actions(
    analysis: SalesCopilotAnalysis, original_text: str
) -> SalesCopilotAnalysis:
    """
    Enforce hard constraints:
    1. Never authorize commercial actions (price matching, discounts).
    2. Never provide medical diagnosis for illness or damaged food packs.
    """
    text_lower = original_text.lower()
    rec_lower = analysis.recommended_next_action.lower()

    # Commercial actions
    if "price match" in text_lower or "discount" in text_lower:
        if (
            "match price" in rec_lower
            or "grant discount" in rec_lower
            or "approve" in rec_lower
            or "authorize" in rec_lower
        ):
            analysis.recommended_next_action = (
                "Log competitor pricing report and request verifiable evidence (promotional flyer or receipt). "
                "Escalate to Commercial Pricing Manager; unauthorized field price matching is strictly prohibited."
            )
            analysis.needs_human_review = True
            analysis.review_reason = (
                "Commercial authorization request: Field price matching requires Commercial Manager approval."
            )

    # Medical diagnosis - prevent making a clinical diagnosis or prescribing treatments
    clinical_patterns = [
        r"diagnosed\s+with",
        r"confirmed\s+(food\s+poisoning|gastroenteritis|infection)",
        r"prescrib(e|ed|ing)",
        r"administer\s+(medicine|drugs|treatment)",
    ]
    if "unwell" in text_lower or "sick" in text_lower or "damaged juice" in text_lower or "poison" in text_lower:
        # Guarantee no unauthorized clinical diagnosis is made
        for pattern in clinical_patterns:
            if re.search(pattern, rec_lower):
                analysis.recommended_next_action = (
                    "Immediately quarantine remaining stock of the affected batch at the outlet. "
                    "Halt further sales, collect packaging sample for QA investigation, and escalate to Quality Assurance and Food Safety. "
                    "Refer unwell individual to licensed healthcare professionals."
                )
                break
        
        analysis.issue_category = IssueCategory.PRODUCT_QUALITY_SAFETY
        analysis.urgency = UrgencyLevel.CRITICAL
        analysis.needs_human_review = True
        analysis.review_reason = (
            "Health & Safety alert: Customer illness reported with damaged product packaging; requires immediate QA escalation."
        )

    return analysis


def enforce_human_review_policy(
    analysis: SalesCopilotAnalysis, matched_records: List[Dict[str, Any]], original_text: str
) -> SalesCopilotAnalysis:
    """
    Enforce defensible human-review policy:
    - Quality & Safety issues -> Mandatory Human Review (CRITICAL)
    - Prompt Injection / Security -> Mandatory Human Review (HIGH/CRITICAL)
    - Inventory Discrepancy (e.g., reported 0, system has 48) -> Mandatory Human Review
    - Commercial Price changes -> Mandatory Human Review
    - High or Critical urgency -> Mandatory Human Review
    """
    reasons = []

    if analysis.issue_category == IssueCategory.PRODUCT_QUALITY_SAFETY:
        reasons.append("Potential health or safety incident requiring Quality Assurance review")
    elif analysis.issue_category == IssueCategory.PROMPT_INJECTION_SECURITY:
        reasons.append("Security exception: adversarial prompt injection or instruction override detected")
    elif analysis.issue_category == IssueCategory.INVENTORY_DISCREPANCY:
        reasons.append("Physical inventory conflict with ERP system stock; requires physical cycle count audit")
    elif analysis.issue_category == IssueCategory.COMPETITOR_ACTIVITY:
        if "price match" in original_text.lower() or "discount" in original_text.lower():
            reasons.append("Commercial policy constraint: Field price adjustments require Commercial Manager authorization")

    if analysis.evidence.conflicts:
        reasons.append("Unresolved conflicts between field update and verified system records")

    if analysis.urgency in [UrgencyLevel.CRITICAL, UrgencyLevel.HIGH]:
        if not reasons:
            reasons.append(f"High operational urgency ({analysis.urgency.value}) requires supervisor sign-off")

    if reasons:
        analysis.needs_human_review = True
        if not analysis.review_reason:
            analysis.review_reason = "; ".join(reasons)
        else:
            # Combine if not already present
            existing = analysis.review_reason
            for r in reasons:
                if r.lower() not in existing.lower():
                    existing += f"; {r}"
            analysis.review_reason = existing

    return analysis
