"""FastAPI REST API application for SalesEasy Copilot with rate-limiting and security controls."""
import time
from collections import defaultdict
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

from app.models import AnalyzeRequest, SalesCopilotAnalysis
from app.copilot import SalesCopilot
from app.evaluator import Evaluator, TEST_SCENARIOS


# In-memory sliding window rate limiter
RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
request_timestamps = defaultdict(list)


def check_rate_limit(request: Request):
    """Basic IP-based rate limiting to satisfy submission security requirements."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timestamps = request_timestamps[client_ip]

    # Remove timestamps older than window
    request_timestamps[client_ip] = [ts for ts in timestamps if now - ts < RATE_LIMIT_WINDOW_SECONDS]

    if len(request_timestamps[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a minute before sending further updates.",
        )

    request_timestamps[client_ip].append(now)


app = FastAPI(
    title="SalesEasy Copilot API",
    description="FMCG Field-Sales AI Copilot with Grounded Evidence Traceability and Human Review Escrow",
    version="2.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

copilot = SalesCopilot()
evaluator = Evaluator(copilot=copilot)


@app.get("/health")
def health():
    return copilot.get_system_status()


@app.get("/api/inventory")
def get_inventory():
    """Retrieve verified ground-truth inventory table."""
    return copilot.get_verified_inventory()


@app.get("/api/scenarios")
def get_scenarios():
    """Return list of standard test scenarios (5 required + 3 custom)."""
    return [
        {
            "id": sc["id"],
            "name": sc["name"],
            "input_text": sc["input_text"],
            "expected_category": sc["expected_category"].value,
            "expected_urgency": sc["expected_urgency"].value,
            "expected_review": sc["expected_review"],
            "description": sc["description"],
            "force_mode": sc.get("force_mode", "auto"),
        }
        for sc in TEST_SCENARIOS
    ]


@app.post("/api/analyze", response_model=SalesCopilotAnalysis)
def analyze_update(req: AnalyzeRequest, _=Depends(check_rate_limit)):
    """
    Analyze plain-text field update.
    Returns structured JSON with category, urgency, traceable evidence, bounded action,
    missing information, and defensible human review escalation.
    """
    if len(req.field_update.strip()) < 3:
        raise HTTPException(status_code=400, detail="Field update too short to analyze.")
    if len(req.field_update) > 5000:
        raise HTTPException(status_code=400, detail="Field update exceeds 5000 character limit.")

    return copilot.process_field_update(req)


@app.post("/api/evaluate")
def run_evaluation(_=Depends(check_rate_limit)):
    """Run full automated evaluation harness on all 8 test scenarios."""
    return evaluator.run_all_evaluations()


@app.get("/api/iteration")
def get_iteration():
    """Get documented evaluation weakness, engineering changes, and before/after comparison."""
    return evaluator.get_iteration_showcase()


# Mount static directory and root React UI
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def serve_ui():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>SalesEasy Copilot Backend is running</h1>"

