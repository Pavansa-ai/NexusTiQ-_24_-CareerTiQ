# Investigator Guidance — Banking Transaction Risk Investigation Assistant

## System Overview

The Banking Transaction Risk Investigation Assistant is a decision-support tool. It does NOT make fraud determinations. It identifies risk signals — patterns in transaction data that deviate from a customer's established behaviour and warrant human review.

## Fundamental Principles

### The System Flags, You Decide
All output from this system is preliminary. The final determination of whether fraudulent or unauthorized activity has occurred rests entirely with the human investigator. Never use system output as the sole basis for customer-adverse action.

### Risk Signal vs. Fraud
The system uses the term **"risk signal"** or **"investigation priority"** intentionally. Phrases like "fraud probability" or "this is fraud" are never appropriate at this stage.

### Evidence Traceability
Every finding in the report is traceable to specific transaction IDs. Investigators should always verify findings against the core banking system before acting.

## Investigation Priority Score

The investigation priority score (0–100) guides workload prioritization:

| Score | Level | Suggested Response |
|-------|-------|-------------------|
| 0–29 | Low | Standard monitoring; no immediate action |
| 30–59 | Medium | Secondary review within 24–48 hours |
| 60–79 | High | Investigation within same business day |
| 80–100 | Critical | Immediate investigation; consider temporary hold |

The score is additive across triggered rules. It is NOT a probability of fraud.

## Baseline Confidence Levels

| Level | Historical Transactions | Implication |
|-------|-------------------------|-------------|
| HIGH | ≥ 30 | Reliable baseline; findings are well-supported |
| MEDIUM | 15–29 | Reasonable baseline; use findings with moderate confidence |
| LOW | 5–14 | Weak baseline; findings are directional only |
| INSUFFICIENT | < 5 | Baseline cannot be established; use manual judgment |

When confidence is LOW or INSUFFICIENT, be more cautious before taking customer-adverse action.

## Standard Investigation Workflow

1. **Review the summary** — understand which rules triggered and at what severity
2. **Examine the flagged transactions** — verify in the core banking system
3. **Review the cluster** — understand which transactions are connected
4. **Check the baseline** — understand what "normal" looks like for this customer
5. **Contact the customer** via verified channel
6. **Document everything** — all contact attempts, customer responses, supporting evidence
7. **Make a determination** — legitimate / inconclusive / escalate / refer to FCU

## When to Escalate

Escalate to the Fraud Control Unit if:
- The customer denies initiating any flagged transactions
- The customer reports being coached or deceived by a third party
- Transaction amounts or patterns suggest imminent account liquidation
- The investigation priority score is CRITICAL (80+) with multiple corroborating signals

## Language and Communication

When communicating with the customer:
- Do NOT use the word "fraud" unless the investigation has concluded and FCU has confirmed
- Use terms like: "unusual activity", "transactions that need verification", "security check"
- Verify identity rigorously before disclosing transaction details

## AI-Generated Explanations

The Gemini AI explanations in this system:
- Are grounded in verified, deterministic evidence
- Are supported by retrieved policy documents (shown in the grounding section)
- Should be read as a professional summary, not as a definitive conclusion
- May be unavailable if the API key is not configured — in that case, deterministic findings still apply

## Data Privacy

Transaction data is sensitive. Do not:
- Share investigation reports with unauthorized parties
- Screenshot or copy transaction data outside approved systems
- Use customer transaction data for any purpose other than the authorized investigation
