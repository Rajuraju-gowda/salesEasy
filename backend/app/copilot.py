"""Core SalesEasy Copilot Orchestrator."""
from typing import Optional, Dict, Any, List
from app.models import SalesCopilotAnalysis, AnalyzeRequest
from app.database import find_matching_records, get_all_inventory
from app.llm_adapter import LLMAdapter


class SalesCopilot:
    def __init__(self):
        self.llm_adapter = LLMAdapter()

    def process_field_update(self, request: AnalyzeRequest) -> SalesCopilotAnalysis:
        """
        Orchestrate the end-to-end processing pipeline:
        1. Query verified ground-truth inventory database for matching stores & SKUs.
        2. Invoke LLM adapter (Live or Deterministic Copilot Engine).
        3. Enforce safety, evidence traceability, and human review defensibility.
        4. Return validated SalesCopilotAnalysis.
        """
        # Step 1: Ground against verified database
        verified_matches = find_matching_records(
            text=request.field_update, outlet_hint=request.outlet_hint
        )

        # Step 2: Run LLM analysis with grounding context
        analysis = self.llm_adapter.analyze(
            field_update=request.field_update,
            verified_records=verified_matches,
            force_mode=request.force_mode or "auto",
            outlet_hint=request.outlet_hint,
        )

        return analysis

    def get_verified_inventory(self):
        return get_all_inventory()

    def get_system_status(self) -> Dict[str, Any]:
        return {
            "status": "online",
            "active_provider": self.llm_adapter.get_active_provider(),
            "default_model": self.llm_adapter.default_model,
            "has_gemini_key": bool(self.llm_adapter.gemini_api_key),
            "has_openai_key": bool(self.llm_adapter.openai_api_key),
        }
