"""
Investigation service — main orchestration layer.

Runs the full pipeline:
  1. Validate & parse CSV
  2. Compute baseline
  3. Build verified evidence (deterministic)
  4. Query local RAG
  5. Gemini reasoning (if available + not cached)
  6. Validate AI output
  7. Return final InvestigationReport

Gemini is never required — the system degrades gracefully.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from src.ai.embeddings import EmbeddingIndex
from src.ai.gemini_client import get_client
from src.ai.output_validator import validate_gemini_output
from src.ai.prompt_builder import build_investigation_prompt, build_no_attention_prompt
from src.ai.retrieval import build_retrieval_query, retrieve_relevant_chunks
from src.core.baseline import compute_baseline
from src.core.evidence import build_evidence
from src.core.report import build_deterministic_report
from src.core.validation import validate_and_parse
from src.models.transaction import (
    AnalyzeResponse,
    InvestigationReport,
    InvestigationStatus,
)

logger = logging.getLogger(__name__)

CACHE_DB = Path("data/cache.db")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _init_cache() -> None:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CACHE_DB)
    con.execute(
        "CREATE TABLE IF NOT EXISTS ai_cache "
        "(hash TEXT PRIMARY KEY, response TEXT, created_at TEXT)"
    )
    con.commit()
    con.close()


def _cache_get(evidence_hash: str) -> Optional[dict]:
    try:
        con = sqlite3.connect(CACHE_DB)
        row = con.execute(
            "SELECT response FROM ai_cache WHERE hash = ?", (evidence_hash,)
        ).fetchone()
        con.close()
        if row:
            return json.loads(row[0])
    except Exception as exc:
        logger.warning(f"Cache read failed: {exc}")
    return None


def _cache_put(evidence_hash: str, response: dict) -> None:
    try:
        con = sqlite3.connect(CACHE_DB)
        from datetime import datetime
        con.execute(
            "INSERT OR REPLACE INTO ai_cache (hash, response, created_at) VALUES (?,?,?)",
            (evidence_hash, json.dumps(response), datetime.utcnow().isoformat()),
        )
        con.commit()
        con.close()
    except Exception as exc:
        logger.warning(f"Cache write failed: {exc}")


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------

def analyze_transactions(
    csv_content: str,
    customer_name: str,
    embedding_index: Optional[EmbeddingIndex],
) -> AnalyzeResponse:
    """
    Full investigation pipeline.  Always returns a response — never crashes.
    """
    _init_cache()

    # 1. Validate & parse
    val_result = validate_and_parse(csv_content)
    if not val_result.is_valid:
        return AnalyzeResponse(
            success=False,
            error="; ".join(val_result.errors),
            validation_warnings=val_result.warnings,
        )

    transactions = val_result.transactions

    # 2. Baseline
    baseline = compute_baseline(transactions)

    # 3. Verified evidence (deterministic)
    evidence, pattern_breakdown = build_evidence(transactions, baseline, customer_name)

    # 4. No-attention fast path — skip Gemini
    needs_gemini = (evidence.investigation_status == InvestigationStatus.ATTENTION_REQUIRED)

    # Check cache
    cached_ai = None
    if needs_gemini:
        cached_ai = _cache_get(evidence.evidence_hash)

    client = get_client()
    ai_available = client.available

    ai_summary = ""
    ai_why = ""
    ai_diff = ""
    ai_steps: list[str] = []
    ai_docs: list[str] = []
    ai_cached = False
    ai_used = False
    deterministic_fallback = False

    if cached_ai:
        # Use cached response
        ai_summary = cached_ai.get("summary", "")
        ai_why = cached_ai.get("why_attention_required", "")
        ai_diff = cached_ai.get("behavioural_difference", "")
        ai_steps = cached_ai.get("investigator_first_steps", [])
        ai_docs = cached_ai.get("retrieved_documents", [])
        ai_cached = True
        ai_used = True
        logger.info(f"Using cached AI response for hash {evidence.evidence_hash[:8]}.")

    elif needs_gemini and ai_available:
        # 5. Retrieve relevant policy chunks
        query = build_retrieval_query(
            triggered_rule_ids=[r.rule_id for r in evidence.triggered_rules],
            payees=[t.payee for t in evidence.flagged_transactions[:5]],
        )
        retrieved = []
        if embedding_index:
            retrieved = retrieve_relevant_chunks(embedding_index, query)
        ai_docs = list({f"{c.source_file} — {c.section_title}" for c in retrieved})

        # 6. Build prompt
        prompt = build_investigation_prompt(evidence, retrieved)

        # 7. Call Gemini
        raw_response = client.generate(prompt, temperature=0.15, max_output_tokens=800)

        if raw_response:
            # 8. Validate AI output
            gemini_out, errors = validate_gemini_output(raw_response, evidence)
            if gemini_out and not errors:
                gemini_out.retrieved_documents = ai_docs
                ai_summary = gemini_out.summary
                ai_why = gemini_out.why_attention_required
                ai_diff = gemini_out.behavioural_difference
                ai_steps = gemini_out.investigator_first_steps
                ai_used = True
                # Cache
                _cache_put(
                    evidence.evidence_hash,
                    {
                        "summary": ai_summary,
                        "why_attention_required": ai_why,
                        "behavioural_difference": ai_diff,
                        "investigator_first_steps": ai_steps,
                        "retrieved_documents": ai_docs,
                    },
                )
            else:
                logger.warning(f"AI output validation failed: {errors}. Using fallback.")
                deterministic_fallback = True
        else:
            logger.warning("Gemini returned no response. Using fallback.")
            deterministic_fallback = True

    elif not needs_gemini:
        # Normal case — brief Gemini confirmation (optional, keep cheap)
        # Skip Gemini call entirely for normal case to save tokens
        ai_used = False

    else:
        # ai_available is False
        deterministic_fallback = True

    # 9. Build deterministic fallback report if AI wasn't used
    if deterministic_fallback or not ai_used:
        fallback_report = build_deterministic_report(
            evidence=evidence,
            pattern_breakdown=pattern_breakdown,
            ai_available=ai_available and not deterministic_fallback,
        )
        ai_summary = fallback_report.ai_summary
        ai_why = fallback_report.ai_why_attention
        ai_diff = fallback_report.ai_behavioural_difference
        ai_steps = fallback_report.ai_first_steps

    # 10. Final report
    report = InvestigationReport(
        investigation_status=evidence.investigation_status,
        priority_score=evidence.priority_score,
        priority_level=evidence.priority_level,
        baseline_confidence=evidence.baseline_confidence,
        customer_name=evidence.customer_name,
        analysis_period=evidence.analysis_period,
        total_transactions=evidence.total_transactions,
        triggered_rules=evidence.triggered_rules,
        flagged_transactions=evidence.flagged_transactions,
        clusters=evidence.clusters,
        baseline=evidence.baseline,
        deviations=evidence.deviations,
        pattern_deviation=pattern_breakdown,
        ai_summary=ai_summary,
        ai_why_attention=ai_why,
        ai_behavioural_difference=ai_diff,
        ai_first_steps=ai_steps,
        ai_grounding_documents=ai_docs,
        ai_available=ai_available,
        ai_cached=ai_cached,
        deterministic_fallback=deterministic_fallback or not ai_used,
        evidence_hash=evidence.evidence_hash,
    )

    return AnalyzeResponse(
        success=True,
        report=report,
        validation_warnings=val_result.warnings,
    )
