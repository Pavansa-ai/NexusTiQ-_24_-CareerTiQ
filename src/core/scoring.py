"""
Investigation Priority Score — deterministic, capped at 0–100.
Never called 'Fraud Score'.  Never called 'Fraud Probability'.
"""
from __future__ import annotations

from src.models.transaction import InvestigationStatus, RiskLevel, TriggeredRule

# ---------------------------------------------------------------------------
# Score interpretation
# ---------------------------------------------------------------------------

SCORE_LOW_MAX = 29
SCORE_MEDIUM_MAX = 59
SCORE_HIGH_MAX = 79
# 80–100 → CRITICAL


def compute_priority_score(triggered_rules: list[TriggeredRule]) -> int:
    """
    Sum score contributions from triggered rules, capped at 100.
    Each rule already carries its score_contribution.
    De-duplicate: if same rule_id fires multiple times (e.g., R1 on multiple txns),
    take the max contribution for that rule_id.
    """
    best_per_rule: dict[str, int] = {}
    for rule in triggered_rules:
        rule_id = rule.rule_id
        best_per_rule[rule_id] = max(
            best_per_rule.get(rule_id, 0), rule.score_contribution
        )

    total = sum(best_per_rule.values())
    return min(100, total)


def get_risk_level(score: int) -> RiskLevel:
    if score <= SCORE_LOW_MAX:
        return RiskLevel.LOW
    elif score <= SCORE_MEDIUM_MAX:
        return RiskLevel.MEDIUM
    elif score <= SCORE_HIGH_MAX:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL


def determine_investigation_status(
    score: int,
    triggered_rules: list[TriggeredRule],
) -> InvestigationStatus:
    """
    Deterministic attention decision.
    Attention required when:
      priority_score >= 30
      AND (at least 2 meaningful rules triggered OR one high/extreme rule)
    """
    if score < 30:
        return InvestigationStatus.NO_ATTENTION_REQUIRED

    # Count unique rule IDs with at least SIGNIFICANT severity
    meaningful_rule_ids = {
        r.rule_id
        for r in triggered_rules
        if r.severity in ("SIGNIFICANT", "STRONG", "EXTREME")
    }

    high_severity_present = any(
        r.severity in ("STRONG", "EXTREME") for r in triggered_rules
    )

    if len(meaningful_rule_ids) >= 2 or high_severity_present:
        return InvestigationStatus.ATTENTION_REQUIRED

    # Score high enough without multiple rules — still require attention
    if score >= 60:
        return InvestigationStatus.ATTENTION_REQUIRED

    return InvestigationStatus.NO_ATTENTION_REQUIRED
