"""
Tests for scoring and AI output validator.
"""
import pytest
from src.core.scoring import compute_priority_score, get_risk_level, determine_investigation_status
from src.ai.output_validator import validate_gemini_output
from src.models.transaction import (
    RiskLevel, InvestigationStatus, TriggeredRule,
    VerifiedEvidence, FlaggedTransaction, BaselineConfidence,
)


# ===========================================================================
# Scoring
# ===========================================================================

class TestScoring:
    def _make_rule(self, rule_id: str, contribution: int, severity: str = "SIGNIFICANT") -> TriggeredRule:
        return TriggeredRule(
            rule_id=rule_id,
            name=f"Rule {rule_id}",
            severity=severity,
            reason="Test",
            transaction_ids=["TX001"],
            score_contribution=contribution,
        )

    def test_score_caps_at_100(self):
        rules = [
            self._make_rule("R1", 35, "EXTREME"),
            self._make_rule("R2", 40, "EXTREME"),
            self._make_rule("R3", 15),
            self._make_rule("R4", 30, "STRONG"),
        ]
        score = compute_priority_score(rules)
        assert score == 100

    def test_score_deduplicates_same_rule_id(self):
        """If R1 fires twice with 25 and 35, only take max (35)."""
        rules = [
            self._make_rule("R1", 25),
            self._make_rule("R1", 35, "EXTREME"),
        ]
        score = compute_priority_score(rules)
        assert score == 35

    def test_risk_level_low(self):
        assert get_risk_level(20) == RiskLevel.LOW

    def test_risk_level_medium(self):
        assert get_risk_level(45) == RiskLevel.MEDIUM

    def test_risk_level_high(self):
        assert get_risk_level(70) == RiskLevel.HIGH

    def test_risk_level_critical(self):
        assert get_risk_level(85) == RiskLevel.CRITICAL

    def test_attention_required_with_two_rules(self):
        rules = [
            self._make_rule("R1", 25),
            self._make_rule("R2", 25),
        ]
        status = determine_investigation_status(50, rules)
        assert status == InvestigationStatus.ATTENTION_REQUIRED

    def test_no_attention_below_30(self):
        rules = [self._make_rule("R3", 15)]
        status = determine_investigation_status(15, rules)
        assert status == InvestigationStatus.NO_ATTENTION_REQUIRED


# ===========================================================================
# AI Output Validator
# ===========================================================================

def make_evidence(flagged_ids: list[str] = None) -> VerifiedEvidence:
    flagged_ids = flagged_ids or ["TX104", "TX105"]
    flagged = [
        FlaggedTransaction(
            transaction_id=tid,
            timestamp="2026-01-19T02:14:00",
            description="Transfer",
            payee="Test Vendor",
            amount=45000.0,
            channel="IMPS",
            triggered_rules=["R2"],
        )
        for tid in flagged_ids
    ]
    return VerifiedEvidence(
        investigation_status=InvestigationStatus.ATTENTION_REQUIRED,
        priority_score=75,
        priority_level=RiskLevel.HIGH,
        baseline_confidence=BaselineConfidence.HIGH,
        triggered_rules=[],
        flagged_transactions=flagged,
        clusters=[],
        baseline={"median_amount": 1000.0},
        deviations={},
        evidence_hash="testhash",
    )


class TestOutputValidator:
    def test_valid_response_passes(self):
        raw = '{"summary": "Test summary.", "why_attention_required": "Multiple signals.", "behavioural_difference": "Normal is X.", "investigator_first_steps": ["Check TX104", "Verify payee"]}'
        evidence = make_evidence()
        output, errors = validate_gemini_output(raw, evidence)
        assert output is not None
        assert errors == []

    def test_malformed_json_fails(self):
        raw = "this is not json"
        evidence = make_evidence()
        output, errors = validate_gemini_output(raw, evidence)
        assert output is None
        assert len(errors) > 0

    def test_missing_field_fails(self):
        raw = '{"summary": "Test"}'  # missing required fields
        evidence = make_evidence()
        output, errors = validate_gemini_output(raw, evidence)
        assert output is None
        assert any("why_attention_required" in e for e in errors)

    def test_fraud_claim_rejected(self):
        raw = '{"summary": "This is fraud.", "why_attention_required": "Fraud has occurred.", "behavioural_difference": "X", "investigator_first_steps": ["Do something"]}'
        evidence = make_evidence()
        output, errors = validate_gemini_output(raw, evidence)
        assert output is None
        assert any("fraud" in e.lower() for e in errors)

    def test_hallucinated_transaction_id_redacted(self):
        raw = '{"summary": "TX999 is suspicious.", "why_attention_required": "TX999 transfers.", "behavioural_difference": "Normal is small.", "investigator_first_steps": ["Check TX999"]}'
        evidence = make_evidence(["TX104", "TX105"])  # TX999 not in evidence
        output, errors = validate_gemini_output(raw, evidence)
        # Should still return output but with TX999 redacted
        assert output is not None
        assert "TX999" not in output.summary or "[REDACTED]" in output.summary

    def test_markdown_json_fence_stripped(self):
        raw = '```json\n{"summary": "Ok.", "why_attention_required": "R2.", "behavioural_difference": "Changed.", "investigator_first_steps": ["Step 1"]}\n```'
        evidence = make_evidence()
        output, errors = validate_gemini_output(raw, evidence)
        assert output is not None
        assert errors == []
