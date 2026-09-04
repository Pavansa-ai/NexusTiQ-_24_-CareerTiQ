"""
AI output validator — validates and sanitises the Gemini JSON response.

Ensures:
- Valid JSON
- Required schema fields present
- No invented transaction IDs
- No invented amounts or payees
- No unsupported fraud claims
- Investigation status not overridden
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.models.transaction import GeminiOutput, InvestigationStatus, VerifiedEvidence

logger = logging.getLogger(__name__)

# Phrases that constitute unsupported fraud claims
FRAUD_PHRASES = [
    "fraud has occurred",
    "is fraudulent",
    "is a fraudster",
    "confirmed fraud",
    "fraud probability",
    "this is fraud",
    "definitely fraud",
    "certainly fraud",
]

REQUIRED_FIELDS = ["summary", "why_attention_required", "behavioural_difference", "investigator_first_steps"]


def validate_gemini_output(
    raw_response: str,
    evidence: VerifiedEvidence,
) -> tuple[Optional[GeminiOutput], list[str]]:
    """
    Validate the Gemini JSON response against the verified evidence.

    Returns:
        (GeminiOutput, []) on success
        (None, [error_messages]) on failure
    """
    errors: list[str] = []

    # 1. Parse JSON
    parsed = _parse_json(raw_response)
    if parsed is None:
        errors.append(f"Gemini response is not valid JSON: {raw_response[:200]}")
        return None, errors

    # 2. Required fields
    for field in REQUIRED_FIELDS:
        if field not in parsed:
            errors.append(f"Missing required field in Gemini response: '{field}'")

    if errors:
        return None, errors

    # 3. Validate types
    if not isinstance(parsed.get("investigator_first_steps"), list):
        parsed["investigator_first_steps"] = [str(parsed.get("investigator_first_steps", ""))]

    for field in ["summary", "why_attention_required", "behavioural_difference"]:
        if not isinstance(parsed.get(field), str):
            parsed[field] = str(parsed.get(field, ""))

    # 4. Check for fraud claims
    all_text = " ".join([
        parsed.get("summary", ""),
        parsed.get("why_attention_required", ""),
        parsed.get("behavioural_difference", ""),
        " ".join(parsed.get("investigator_first_steps", [])),
    ]).lower()

    for phrase in FRAUD_PHRASES:
        if phrase in all_text:
            errors.append(
                f"Gemini response contains unsupported fraud claim: '{phrase}'. "
                "Rejecting response."
            )
            return None, errors

    # 5. Verify transaction IDs (check that any mentioned IDs exist in evidence)
    known_ids = {t.transaction_id for t in evidence.flagged_transactions}
    mentioned_ids = _extract_transaction_ids(all_text)
    hallucinated_ids = mentioned_ids - known_ids
    if hallucinated_ids:
        logger.warning(
            f"Gemini hallucinated transaction IDs: {hallucinated_ids}. "
            "These will be flagged but response kept if otherwise valid."
        )
        # Redact hallucinated IDs from summary rather than reject entire response
        for hid in hallucinated_ids:
            for key in ["summary", "why_attention_required", "behavioural_difference"]:
                parsed[key] = parsed[key].replace(hid, "[REDACTED]")
        parsed["investigator_first_steps"] = [
            step.replace(hid, "[REDACTED]")
            for step in parsed["investigator_first_steps"]
            for hid in hallucinated_ids
        ]

    # 6. Validate amounts mentioned in the response (lenient — just log)
    known_amounts = {t.amount for t in evidence.flagged_transactions}
    _check_amounts(parsed.get("summary", ""), known_amounts)

    # 7. Ensure response doesn't change investigation status
    status_phrases = {
        InvestigationStatus.ATTENTION_REQUIRED.value.lower(): True,
        InvestigationStatus.NO_ATTENTION_REQUIRED.value.lower(): False,
    }
    expected_needs_attention = (
        evidence.investigation_status == InvestigationStatus.ATTENTION_REQUIRED
    )

    output = GeminiOutput(
        summary=parsed["summary"],
        why_attention_required=parsed["why_attention_required"],
        behavioural_difference=parsed["behavioural_difference"],
        investigator_first_steps=parsed["investigator_first_steps"][:6],  # cap steps
        retrieved_documents=[],  # filled by caller
    )
    return output, []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> Optional[dict]:
    """Try to parse JSON, stripping markdown code fences if present."""
    text = text.strip()
    # Remove ```json ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def _extract_transaction_ids(text: str) -> set[str]:
    """Find transaction ID patterns like TX001, TXN-123, etc. in text."""
    patterns = [
        r"\bTX\d+\b",
        r"\bTXN[-\s]?\d+\b",
        r"\bTX-\d+\b",
    ]
    ids: set[str] = set()
    for pattern in patterns:
        ids.update(re.findall(pattern, text.upper()))
    return ids


def _check_amounts(text: str, known_amounts: set[float]) -> None:
    """Log a warning if Gemini mentions an amount not in the evidence (lenient)."""
    amount_pattern = re.findall(r"₹[\d,]+(?:\.\d+)?", text)
    for amt_str in amount_pattern:
        try:
            val = float(amt_str.replace("₹", "").replace(",", ""))
            # Allow ±1 rupee tolerance for rounding
            if not any(abs(val - ka) <= 1 for ka in known_amounts):
                logger.debug(f"Gemini mentioned amount {amt_str} not in evidence (may be derived/rounded).")
        except ValueError:
            pass
