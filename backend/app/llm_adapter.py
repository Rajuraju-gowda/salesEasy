"""LLM Adapter supporting Live Google Gemini API calls and a high-fidelity deterministic Mock Engine."""
import os
import re
import json
import time
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from typing import Dict, Any, List, Optional, Tuple
from app.models import (
    SalesCopilotAnalysis,
    IssueCategory,
    UrgencyLevel,
    EvidenceModel,
)
from app.prompt import SYSTEM_PROMPT, format_user_prompt
from app.guardrails import (
    detect_prompt_injection,
    check_for_fabricated_numbers,
    sanitize_commercial_and_medical_actions,
    enforce_human_review_policy,
)


class LLMAdapter:
    def __init__(self):
        load_dotenv()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.default_model = "live_gemini" if self.gemini_api_key else "rule_assisted_mock"

    def get_active_provider(self) -> str:
        if self.gemini_api_key:
            return "live_gemini (Google Gemini 1.5/2.0 API)"
        return "rule_assisted_mock (Deterministic Copilot Engine)"

    def analyze(
        self,
        field_update: str,
        verified_records: List[Dict[str, Any]],
        force_mode: str = "auto",
        outlet_hint: Optional[str] = None,
    ) -> SalesCopilotAnalysis:
        start_time = time.time()

        # Check for simulated failure mode (Scenario 7)
        if force_mode == "simulate_failure":
            return self._handle_graceful_fallback(
                field_update=field_update,
                verified_records=verified_records,
                error_message="Simulated Upstream LLM Gateway Timeout (504 Gateway Timeout)",
                start_time=start_time,
            )

        # 1. Pre-execution Prompt Injection Guardrail
        is_injection, injection_reason = detect_prompt_injection(field_update)
        if is_injection:
            analysis = SalesCopilotAnalysis(
                issue_category=IssueCategory.PROMPT_INJECTION_SECURITY,
                urgency=UrgencyLevel.HIGH,
                evidence=EvidenceModel(
                    verified_facts=[
                        f"Database contains {len(verified_records)} matched store record(s)"
                    ] if verified_records else ["No matching store records queried"],
                    unverified_claims=[
                        f"Field update attempted adversarial instruction override: '{field_update.strip()}'"
                    ],
                    conflicts=[
                        "Adversarial request attempting to override system behavior and force low urgency"
                    ],
                ),
                recommended_next_action=(
                    "Quarantine update immediately; log adversarial security incident. "
                    "Do NOT mark as resolved or low urgency; route to system compliance for investigation."
                ),
                missing_information=[],
                needs_human_review=True,
                review_reason=f"Security alert: {injection_reason}",
                model_mode="guardrail_pre_execution",
                latency_ms=round((time.time() - start_time) * 1000, 2),
            )
            return analysis

        # Determine execution engine
        selected_mode = force_mode if force_mode in ["mock", "live"] else ("live" if self.gemini_api_key else "mock")

        analysis = None
        if selected_mode == "live":
            try:
                if self.gemini_api_key:
                    analysis = self._call_gemini_api(field_update, verified_records, outlet_hint)
            except Exception as e:
                # Upstream LLM failed: Graceful Fallback
                return self._handle_graceful_fallback(
                    field_update=field_update,
                    verified_records=verified_records,
                    error_message=f"Live Gemini API call failed ({str(e)}). Switched to Graceful Safety Fallback.",
                    start_time=start_time,
                )

        # Fallback to or use deterministic copilot engine
        if analysis is None:
            analysis = self._deterministic_copilot_engine(field_update, verified_records, outlet_hint)

        # 2. Post-execution Safety Guardrails
        analysis = check_for_fabricated_numbers(field_update, analysis)
        analysis = sanitize_commercial_and_medical_actions(analysis, field_update)
        analysis = enforce_human_review_policy(analysis, verified_records, field_update)
        analysis.latency_ms = round((time.time() - start_time) * 1000, 2)

        return analysis

    def _call_gemini_api(
        self, field_update: str, verified_records: List[Dict[str, Any]], outlet_hint: Optional[str]
    ) -> SalesCopilotAnalysis:
        """Call Gemini REST API directly with structured response parsing."""
        models_to_try = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
        user_prompt = format_user_prompt(field_update, verified_records, outlet_hint)
        
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        }

        last_error = None
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        # Clean possible markdown wrapping
                        if raw_text.startswith("```json"):
                            raw_text = raw_text[7:]
                        elif raw_text.startswith("```"):
                            raw_text = raw_text[3:]
                        if raw_text.endswith("```"):
                            raw_text = raw_text[:-3]
                        raw_text = raw_text.strip()

                        parsed = json.loads(raw_text)
                        parsed["model_mode"] = f"live_gemini ({model})"
                        return SalesCopilotAnalysis(**parsed)
                    else:
                        last_error = f"Model {model} returned HTTP {resp.status_code}: {resp.text}"
            except Exception as e:
                last_error = str(e)
                continue

        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    def _deterministic_copilot_engine(
        self, field_update: str, verified_records: List[Dict[str, Any]], outlet_hint: Optional[str]
    ) -> SalesCopilotAnalysis:
        """
        High-fidelity deterministic copilot implementation of the system prompt.
        Ensures strict schema compliance, zero hallucinated numbers, conflict detection,
        and traceable evidence.
        """
        text = field_update.strip()
        lower = text.lower()

        # Check for matching store in verified database
        matched_item = verified_records[0] if verified_records else None
        store_name = matched_item["outlet"] if matched_item else None
        sku_name = matched_item["sku"] if matched_item else None
        system_stock = matched_item["system_stock"] if matched_item else None

        # Case 1: Product Quality / Health / Damaged Pack / Customer Unwell (Scenario 5)
        if any(term in lower for term in ["unwell", "sick", "damaged", "illness", "vomit", "leak", "poison"]):
            verified_facts = []
            if matched_item:
                verified_facts.append(
                    f"System records {system_stock} units of {sku_name} at {store_name} as of {matched_item.get('last_verified')}."
                )
            
            return SalesCopilotAnalysis(
                issue_category=IssueCategory.PRODUCT_QUALITY_SAFETY,
                urgency=UrgencyLevel.CRITICAL,
                evidence=EvidenceModel(
                    verified_facts=verified_facts,
                    unverified_claims=[
                        f"Field claim: '{text}' (damaged packaging and customer feeling unwell)"
                    ],
                    conflicts=[],
                ),
                recommended_next_action=(
                    "Immediately quarantine remaining stock of the affected batch at the outlet. "
                    "Halt further sales, secure the damaged package for QA testing, and escalate to the Quality Assurance & Food Safety Officer. "
                    "Refer unwell individual to professional healthcare providers; avoid unauthorized in-store clinical assessments."
                ),
                missing_information=[
                    "Product batch / lot number",
                    "Manufacturing / expiry date",
                    "Customer contact details for welfare follow-up",
                ],
                needs_human_review=True,
                review_reason="Critical food safety & health risk involving customer illness and damaged packaging.",
                model_mode="rule_assisted_mock",
            )

        # Case 2: Competitor discounting / price match demand (Scenario 3)
        if any(term in lower for term in ["price match", "competitor", "discounting", "discount everywhere", "undercutting"]):
            verified_facts = []
            if matched_item:
                verified_facts.append(
                    f"Current system stock at {store_name} is {system_stock} units for {sku_name}."
                )

            return SalesCopilotAnalysis(
                issue_category=IssueCategory.COMPETITOR_ACTIVITY,
                urgency=UrgencyLevel.MEDIUM,
                evidence=EvidenceModel(
                    verified_facts=verified_facts,
                    unverified_claims=[
                        "Rep asserts competitor is discounting everywhere and demands an immediate price match without documentary proof."
                    ],
                    conflicts=[],
                ),
                recommended_next_action=(
                    "Log competitor promotional intelligence; do NOT authorize price match or field discounts. "
                    "Request representative submit photographic evidence or competitor invoice, and escalate report to Commercial Pricing Manager."
                ),
                missing_information=[
                    "Competitor brand name and specific SKU",
                    "Competitor promotional price point",
                    "Proof of promotional flyer, receipt, or shelf-tag photo",
                ],
                needs_human_review=True,
                review_reason="Commercial policy constraint: Field sales reps cannot authorize price adjustments without Commercial Pricing Manager sign-off.",
                model_mode="rule_assisted_mock",
            )

        # Case 3: Inventory Discrepancy / Phantom stock (Scenario 2 - Metro Fresh)
        if matched_item and system_stock > 0 and any(term in lower for term in ["stockout", "out of stock", "unavailable", "empty shelf", "zero stock"]):
            return SalesCopilotAnalysis(
                issue_category=IssueCategory.INVENTORY_DISCREPANCY,
                urgency=UrgencyLevel.HIGH,
                evidence=EvidenceModel(
                    verified_facts=[
                        f"Verified ERP database records {system_stock} units of {sku_name} at {store_name}."
                    ],
                    unverified_claims=[
                        f"Field rep reports a complete stockout/unavailable at {store_name}."
                    ],
                    conflicts=[
                        f"Direct contradiction: Rep reports 0 units / stockout, but system shows {system_stock} units in inventory (potential phantom stock or shrinkage)."
                    ],
                ),
                recommended_next_action=(
                    f"Dispatch field supervisor or inventory auditor to {store_name} for immediate physical cycle count. "
                    "Verify if stock is misplaced in backroom or lost to shrinkage before adjusting system records."
                ),
                missing_information=[
                    "Physical verification timestamp",
                    "Backroom stock count verification",
                    "Auditor badge/staff signature",
                ],
                needs_human_review=True,
                review_reason=f"Significant inventory mismatch: System records {system_stock} units but physical stockout reported.",
                model_mode="rule_assisted_mock",
            )

        # Case 4: Verified Stockout with claims of lost sales (Scenario 1 - Indiranagar Mart)
        if matched_item and system_stock == 0 and any(term in lower for term in ["unavailable", "stockout", "out of stock", "no stock", "empty"]):
            return SalesCopilotAnalysis(
                issue_category=IssueCategory.OUT_OF_STOCK,
                urgency=UrgencyLevel.HIGH,
                evidence=EvidenceModel(
                    verified_facts=[
                        f"Verified database confirms {store_name} has {system_stock} units of {sku_name} (confirmed stockout)."
                    ],
                    unverified_claims=[
                        "Rep claims major lost sales; no quantifiable POS transaction counts or revenue figures provided."
                    ],
                    conflicts=[],
                ),
                recommended_next_action=(
                    f"Initiate standard replenishment dispatch of {sku_name} to {store_name}. "
                    "Request store POS transaction logs to quantify reported lost sales; do not invent or estimate financial impact."
                ),
                missing_information=[
                    "Target replenishment batch size",
                    "Store POS transaction count during stockout window",
                ],
                needs_human_review=True,
                review_reason="Stockout at key retail outlet with unquantified lost sales claims requiring fulfillment prioritization.",
                model_mode="rule_assisted_mock",
            )

        # Case 5: Missing Information Case (Scenario 6)
        # e.g., "We are running low on stock at our main outlet, please send more ASAP"
        has_store = bool(store_name or outlet_hint)
        has_sku = bool(sku_name)
        has_quantity = bool(re.search(r"\b\d+\s*(units?|cases?|packs?|boxes?)?\b", text, re.IGNORECASE))

        if not has_store or not has_sku:
            missing = []
            if not has_store:
                missing.append("Specific retail outlet name / store ID")
            if not has_sku:
                missing.append("Target product SKU / bottle size")
            if not has_quantity:
                missing.append("Required replenishment quantity / current shelf count")

            return SalesCopilotAnalysis(
                issue_category=IssueCategory.OUT_OF_STOCK if "stock" in lower else IssueCategory.GENERAL_FIELD_UPDATE,
                urgency=UrgencyLevel.MEDIUM,
                evidence=EvidenceModel(
                    verified_facts=[
                        "No verified database record could be uniquely resolved due to incomplete field update."
                    ],
                    unverified_claims=[
                        f"Field rep report: '{text}'"
                    ],
                    conflicts=[],
                ),
                recommended_next_action=(
                    "Request immediate clarification from field representative to specify the exact outlet name, "
                    "product SKU, and inventory count before dispatching warehouse stock."
                ),
                missing_information=missing,
                needs_human_review=True,
                review_reason="Action blocked by missing mandatory operational parameters (outlet/SKU/quantity).",
                model_mode="rule_assisted_mock",
            )

        # Case 6: Routine verified update / low risk (Scenario 8)
        if any(term in lower for term in ["routine", "steady", "regular", "normal", "weekly reorder", "scheduled"]):
            return SalesCopilotAnalysis(
                issue_category=IssueCategory.GENERAL_FIELD_UPDATE,
                urgency=UrgencyLevel.LOW,
                evidence=EvidenceModel(
                    verified_facts=[
                        f"System records {system_stock} units of {sku_name} at {store_name}, in agreement with field report."
                    ],
                    unverified_claims=[
                        "Routine operational observations provided by representative."
                    ],
                    conflicts=[],
                ),
                recommended_next_action=(
                    f"Queue standard weekly replenishment for {store_name} ({sku_name}) in next routine dispatch cycle."
                ),
                missing_information=[],
                needs_human_review=False,
                review_reason=None,
                model_mode="rule_assisted_mock",
            )

        # Default fallback categorization
        return SalesCopilotAnalysis(
            issue_category=IssueCategory.GENERAL_FIELD_UPDATE,
            urgency=UrgencyLevel.LOW if (matched_item and system_stock > 10) else UrgencyLevel.MEDIUM,
            evidence=EvidenceModel(
                verified_facts=[
                    f"Matched {store_name} ({sku_name}): {system_stock} units in system."
                ] if matched_item else ["No exact matching inventory record found in database."],
                unverified_claims=[f"Field update: '{text}'"],
                conflicts=[],
            ),
            recommended_next_action="Log field update for operational review and monitor inventory trends.",
            missing_information=[],
            needs_human_review=False if (matched_item and system_stock > 10) else True,
            review_reason=None if (matched_item and system_stock > 10) else "General update requiring supervisor acknowledgment.",
            model_mode="rule_assisted_mock",
        )

    def _handle_graceful_fallback(
        self,
        field_update: str,
        verified_records: List[Dict[str, Any]],
        error_message: str,
        start_time: float,
    ) -> SalesCopilotAnalysis:
        """
        Graceful fallback handler when upstream LLM or network fails.
        Guarantees that the system never crashes, maintains schema integrity,
        and safely escalates to human review.
        """
        verified_facts = []
        for r in verified_records:
            verified_facts.append(f"{r['outlet']} - {r['sku']}: {r['system_stock']} units in ERP")

        return SalesCopilotAnalysis(
            issue_category=IssueCategory.GENERAL_FIELD_UPDATE,
            urgency=UrgencyLevel.HIGH,
            evidence=EvidenceModel(
                verified_facts=verified_facts or ["System records available for lookup"],
                unverified_claims=[f"Raw field update received: '{field_update}'"],
                conflicts=[f"Automated processing degraded: {error_message}"],
            ),
            recommended_next_action=(
                "System operating in Graceful Fallback Mode due to upstream LLM service interruption. "
                "Route field update to human sales coordinator for manual triage and resolution."
            ),
            missing_information=["Full automated AI extraction unavailable during service degradation"],
            needs_human_review=True,
            review_reason=f"Graceful Fallback Engaged: {error_message}",
            model_mode="fallback_safety",
            latency_ms=round((time.time() - start_time) * 1000, 2),
        )
