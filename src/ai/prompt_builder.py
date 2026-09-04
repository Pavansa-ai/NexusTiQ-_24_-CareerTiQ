"""
Prompt builder — constructs compact, token-efficient prompts for Gemini reasoning.

Targets approximately 500–2000 tokens per prompt.
Only sends verified evidence and retrieved policy chunks — never the full CSV.
"""
from __future__ import annotations

import json
from typing import Optional

from src.ai.embeddings import DocumentChunk
from src.models.transaction import InvestigationStatus, VerifiedEvidence

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are an expert banking investigation assistant helping human investigators.

CRITICAL RULES:
1. Use ONLY the evidence provided in <EVIDENCE>. Do NOT invent transaction IDs, amounts, dates, or payees.
2. Use the policy documents in <POLICY_CONTEXT> to interpret investigation rules.
3. NEVER state that fraud has occurred. Use language like "risk signal", "requires investigation", "behaviour deviation".
4. NEVER change the investigation status determined by the system.
5. If evidence is insufficient, explicitly acknowledge this.
6. Recommend escalation to a human investigator when appropriate.
7. Be factual, concise, and professional.

Respond ONLY with valid JSON matching this exact schema:
{
  "summary": "2-3 sentence executive summary for an investigator",
  "why_attention_required": "Explain which specific signals were detected and why they are concerning",
  "behavioural_difference": "Compare the flagged behaviour to the customer's normal baseline",
  "investigator_first_steps": ["step 1", "step 2", "step 3", "step 4"]
}"""


def build_investigation_prompt(
    evidence: VerifiedEvidence,
    retrieved_chunks: list[DocumentChunk],
) -> str:
    """
    Build a compact investigation prompt for Gemini.
    Keeps token count within ~500–2000 input tokens.
    """
    # --- Policy context (retrieved chunks) ---
    policy_text = _format_policy_context(retrieved_chunks)

    # --- Evidence (compact JSON subset) ---
    evidence_dict = _compact_evidence(evidence)

    prompt = f"""{SYSTEM_INSTRUCTION}

<POLICY_CONTEXT>
{policy_text}
</POLICY_CONTEXT>

<EVIDENCE>
{json.dumps(evidence_dict, indent=2, ensure_ascii=False)}
</EVIDENCE>

Based on the EVIDENCE and POLICY_CONTEXT above, produce your investigation analysis as JSON.
Do not include any text outside the JSON object.
"""
    return prompt


def build_no_attention_prompt(evidence: VerifiedEvidence) -> str:
    """
    Minimal prompt for the no-attention case.
    Gemini is only used to provide a brief confirmation — not to re-analyse.
    """
    return f"""{SYSTEM_INSTRUCTION}

The deterministic investigation engine found NO significant risk signals.

<EVIDENCE>
{json.dumps({
    "investigation_status": evidence.investigation_status.value,
    "priority_score": evidence.priority_score,
    "customer_name": evidence.customer_name,
    "analysis_period": evidence.analysis_period,
    "total_transactions": evidence.total_transactions,
    "baseline_confidence": evidence.baseline_confidence.value,
    "baseline_median_amount": evidence.baseline.get("median_amount"),
}, indent=2)}
</EVIDENCE>

Confirm the finding in the JSON schema. Keep "investigator_first_steps" to standard monitoring advice.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_policy_context(chunks: list[DocumentChunk]) -> str:
    if not chunks:
        return "(No policy documents retrieved.)"
    parts: list[str] = []
    for chunk in chunks:
        parts.append(f"[Source: {chunk.source_file} — {chunk.section_title}]\n{chunk.text[:350]}")
    return "\n\n".join(parts)


def _compact_evidence(evidence: VerifiedEvidence) -> dict:
    """
    Build a compact evidence dictionary.
    Only includes what's necessary for Gemini reasoning.
    Hard limit: keep total JSON < ~2000 tokens (~8000 chars).
    """
    triggered_rules_compact = [
        {
            "rule_id": r.rule_id,
            "name": r.name,
            "severity": r.severity,
            "reason": r.reason[:300],  # cap reason length
            "transaction_ids": r.transaction_ids[:10],
        }
        for r in evidence.triggered_rules
    ]

    flagged_txns_compact = [
        {
            "id": t.transaction_id,
            "timestamp": t.timestamp,
            "payee": t.payee,
            "amount": t.amount,
            "channel": t.channel,
            "rules": t.triggered_rules,
        }
        for t in evidence.flagged_transactions[:15]  # cap at 15 transactions
    ]

    clusters_compact = [
        {
            "cluster_id": c.cluster_id,
            "transaction_ids": c.transaction_ids[:10],
            "payee": c.payee,
            "total_amount": c.total_amount,
            "time_span_hours": c.time_span_hours,
            "rules_triggered": c.rules_triggered,
        }
        for c in evidence.clusters[:5]
    ]

    return {
        "investigation_status": evidence.investigation_status.value,
        "priority_score": evidence.priority_score,
        "priority_level": evidence.priority_level.value,
        "baseline_confidence": evidence.baseline_confidence.value,
        "customer_name": evidence.customer_name,
        "analysis_period": evidence.analysis_period,
        "total_transactions": evidence.total_transactions,
        "triggered_rules": triggered_rules_compact,
        "flagged_transactions": flagged_txns_compact,
        "clusters": clusters_compact,
        "baseline_summary": {
            "median_amount": evidence.baseline.get("median_amount"),
            "normal_activity_window": evidence.baseline.get("normal_activity_window"),
            "n_historical": evidence.baseline.get("n_historical"),
            "large_threshold": evidence.baseline.get("large_threshold"),
        },
        "deviations": evidence.deviations,
    }
