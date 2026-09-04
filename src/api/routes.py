"""
FastAPI routes for the Banking Transaction Risk Investigation Assistant.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from src.models.transaction import AnalyzeRequest, AnalyzeResponse, SampleCase

logger = logging.getLogger(__name__)

router = APIRouter()

# Embedding index is set by app.py on startup
_embedding_index = None


def set_embedding_index(index) -> None:
    global _embedding_index
    _embedding_index = index


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    from src.ai.gemini_client import get_client
    client = get_client()
    return {
        "status": "ok",
        "ai_available": client.available,
        "index_loaded": _embedding_index is not None and len(getattr(_embedding_index, "chunks", [])) > 0,
    }


# ---------------------------------------------------------------------------
# Rules reference
# ---------------------------------------------------------------------------

@router.get("/rules")
async def get_rules():
    return {
        "rules": [
            {
                "id": "R1",
                "name": "Unusually Large Transfer",
                "description": "Flags transactions exceeding Q3 + 1.5×IQR AND ≥3× median amount. Extreme version uses Q3 + 3×IQR AND ≥5× median.",
                "score": {"large": 25, "extreme": 35},
            },
            {
                "id": "R2",
                "name": "New Payee Burst",
                "description": "Flags ≥3 transactions to a new payee within 48 hours with total ≥ max(₹50,000, 5×median). Stronger thresholds for 24h/4-txn bursts.",
                "score": {"baseline": 20, "strong": 30, "very_strong": 40},
            },
            {
                "id": "R3",
                "name": "Odd-Hours Activity",
                "description": "Flags transactions outside the customer's established active-hour window ±2h buffer. Only applied when ≥10 historical transactions exist.",
                "score": 15,
            },
            {
                "id": "R4",
                "name": "Behavioural Pattern Deviation",
                "description": "Multi-dimensional weighted score (amount 40%, time 20%, payee 20%, channel 10%, frequency 10%). Triggers at ≥50 score.",
                "score": {"significant": 20, "strong": 30},
                "weights": {
                    "amount": 0.40,
                    "time": 0.20,
                    "payee": 0.20,
                    "channel": 0.10,
                    "frequency": 0.10,
                },
            },
        ]
    }


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

@router.get("/sample/{case_type}")
async def get_sample(case_type: str):
    """Return sample CSV content for normal or investigation case."""
    case_map = {
        "normal": Path("data/normal_case.csv"),
        "investigation": Path("data/investigation_case.csv"),
    }
    path = case_map.get(case_type.lower())
    if not path:
        raise HTTPException(status_code=404, detail=f"Unknown case type: {case_type}")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Sample data not found: {path}")
    return {"csv_content": path.read_text(encoding="utf-8"), "case_type": case_type}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Main analysis endpoint.
    Accepts CSV content and customer name, returns InvestigationReport.
    """
    from src.services.investigation import analyze_transactions

    if not request.csv_content or not request.csv_content.strip():
        raise HTTPException(status_code=400, detail="csv_content is required and must not be empty.")

    try:
        result = analyze_transactions(
            csv_content=request.csv_content,
            customer_name=request.customer_name or "Customer",
            embedding_index=_embedding_index,
        )
        return result
    except Exception as exc:
        logger.exception(f"Unexpected error during analysis: {exc}")
        return AnalyzeResponse(
            success=False,
            error="An unexpected error occurred. Please check server logs.",
        )
