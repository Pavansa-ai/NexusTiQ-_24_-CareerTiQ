# New Payee Burst Investigation Policy

## Purpose

This policy guides investigators when multiple rapid transactions are detected to a payee that has no prior history in the customer's records.

## Why New Payee Bursts Are Significant

Legitimate new payees typically start with a single cautious transaction. Rapid bursts of multiple transactions to a never-before-seen payee — particularly within 24–48 hours — are a recognized pattern in:
- Account takeover scenarios where an attacker quickly empties funds
- Money mule arrangements
- Social engineering attacks where the victim is manipulated to transfer repeatedly
- Unauthorized third-party access

This does NOT mean such a burst is fraudulent. However, it warrants verification.

## What Constitutes a "New Payee"

A payee is classified as new when:
- The payee name has zero occurrences in the customer's transaction history before the current analysis window
- The comparison is normalized (case-insensitive)

A payee who appeared even once historically is NOT considered new.

## Burst Detection Criteria

| Level | Count | Timeframe | Minimum Total |
|-------|-------|-----------|---------------|
| Baseline | ≥ 3 | 48 hours | max(₹50,000, 5× median) |
| Strong | ≥ 3 | 24 hours | max(₹1,00,000, 10× median) |
| Very Strong | ≥ 4 | 24 hours | max(₹2,00,000, 15× median) |

## Investigation Steps

### Immediate Actions
1. Identify the new payee's account details in the core banking system
2. Verify whether the payee is a registered business or individual
3. Check the GSTIN/PAN associated with the payee (for business payments)

### Customer Contact Protocol
- Contact the customer through a verified, pre-registered channel (registered mobile, email)
- Do NOT rely on contact details provided in an unverified session
- Ask the customer to confirm:
  - Whether they initiated each transaction in the burst
  - Their relationship with the payee
  - The purpose of each payment
  - Whether they received any unusual communication before making the transfers

### Escalation Criteria
Escalate to senior investigator or Fraud Control Unit if:
- Customer denies initiating any of the transactions
- Customer confirms being "coached" by a third party
- The payee account itself shows signs of being recently opened or dormant
- The burst coincides with odd-hours activity or device/location changes

## Documentation Requirements

- Record all customer contact attempts and responses
- Document payee identity verification results
- Note the investigation disposition (confirmed legitimate / referred to FCU / blocked)
