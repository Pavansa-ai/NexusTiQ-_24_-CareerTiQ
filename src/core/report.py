"""
Deterministic fallback report generator.

Used when Gemini is unavailable or returns invalid output.
Produces a complete InvestigationReport from the VerifiedEvidence alone.
"""
from __future__ import annotations

from typing import Optional

from src.models.transaction import (
    BaselineConfidence,
    InvestigationReport,
    InvestigationStatus,
    PatternDeviationBreakdown,
    TriggeredRule,
    VerifiedEvidence,
)

RULE_NAMES = {
    "R1": "Unusually Large Transfer",
    "R2": "New Payee Burst",
    "R3": "Odd-Hours Activity",
    "R4": "Behavioural Pattern Deviation",
}

LOW_CONFIDENCE_NOTE = (
    "NOTE: The historical baseline has low confidence "
    "due to limited transaction history. Conclusions should be treated cautiously."
)


def build_deterministic_report(
    evidence: VerifiedEvidence,
    pattern_breakdown: Optional[PatternDeviationBreakdown] = None,
    ai_available: bool = True,
) -> InvestigationReport:
    """
    Build a complete InvestigationReport from verified deterministic data.
    If AI is unavailable, ai_available=False and fallback text is used.
    """
    # ----- Summary text -------------------------------------------------
    if evidence.investigation_status == InvestigationStatus.ATTENTION_REQUIRED:
        summary = _build_attention_summary(evidence)
        why_attention = _build_why_attention(evidence)
        behavioural_diff = _build_behavioural_diff(evidence)
        first_steps = _build_first_steps(evidence)
    else:
        summary = (
            f"Analysis of {evidence.total_transactions} transactions for "
            f"{evidence.customer_name} covering {evidence.analysis_period} "
            "shows no significant risk signals. "
            "Transaction patterns are consistent with the customer's established baseline behaviour."
        )
        why_attention = "No meaningful risk signals were detected by the deterministic engine."
        behavioural_diff = "Current activity is consistent with historical patterns."
        first_steps = [
            "No immediate investigator action required.",
            "Continue standard monitoring procedures.",
        ]

    # ----- Confidence warning -------------------------------------------
    if evidence.baseline_confidence in (
        BaselineConfidence.LOW,
        BaselineConfidence.INSUFFICIENT,
    ):
        summary = f"{LOW_CONFIDENCE_NOTE}\n\n{summary}"

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
        ai_summary=summary,
        ai_why_attention=why_attention,
        ai_behavioural_difference=behavioural_diff,
        ai_first_steps=first_steps,
        ai_grounding_documents=[],
        ai_available=ai_available,
        ai_cached=False,
        deterministic_fallback=not ai_available,
        evidence_hash=evidence.evidence_hash,
    )
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_attention_summary(evidence: VerifiedEvidence) -> str:
    rule_names = [r.name for r in evidence.triggered_rules]
    rule_list = "; ".join(rule_names) if rule_names else "risk signal detected"
    flagged_count = len(evidence.flagged_transactions)
    return (
        f"Investigation Priority Score: {evidence.priority_score}/100 "
        f"({evidence.priority_level.value}). "
        f"{flagged_count} transaction(s) require investigator attention. "
        f"Triggered: {rule_list}. "
        f"Baseline Confidence: {evidence.baseline_confidence.value}."
    )


def _build_why_attention(evidence: VerifiedEvidence) -> str:
    lines: list[str] = []
    for rule in evidence.triggered_rules:
        lines.append(f"• {rule.name} ({rule.severity}): {rule.reason}")
    return "\n".join(lines) if lines else "See triggered rules above."


def _build_behavioural_diff(evidence: VerifiedEvidence) -> str:
    baseline = evidence.baseline
    lines: list[str] = [
        f"Historical median transaction amount: ₹{baseline.get('median_amount', 'N/A'):,.0f}",
        f"Normal activity window: {baseline.get('normal_activity_window', 'N/A')}",
        f"Historical confidence: {baseline.get('confidence', 'N/A')} ({baseline.get('n_historical', 0)} transactions)",
    ]
    if evidence.deviations:
        lines.append("")
        lines.append("Deviation breakdown:")
        for dim, label in evidence.deviations.items():
            if dim != "overall_score":
                lines.append(f"  {dim.capitalize()}: {label}")
    return "\n".join(lines)


def _build_first_steps(evidence: VerifiedEvidence) -> list[str]:
    steps: list[str] = []
    rule_ids = {r.rule_id for r in evidence.triggered_rules}

    if "R2" in rule_ids:
        steps.append(
            "Verify the customer's relationship with the new payee(s) and confirm "
            "transaction intent via callback or secure message."
        )
    if "R1" in rule_ids:
        steps.append(
            "Request supporting documentation for the unusually large transfer(s), "
            "such as an invoice, contract, or payment instruction."
        )
    if "R3" in rule_ids:
        steps.append(
            "Check whether the customer was aware of the odd-hours transaction(s) "
            "and confirm whether any device or location anomaly exists."
        )
    if "R4" in rule_ids:
        steps.append(
            "Review the customer's recent account activity holistically for signs of "
            "account takeover or third-party manipulation."
        )

    steps.append(
        "Cross-reference all flagged transaction IDs in the core banking system "
        "and confirm beneficiary details."
    )
    steps.append(
        "Escalate to senior investigator if the customer cannot be reached for verification."
    )
    return steps
