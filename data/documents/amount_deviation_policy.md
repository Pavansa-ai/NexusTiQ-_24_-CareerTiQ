# Amount Deviation Investigation Policy

## Purpose

This policy governs how investigators should respond to transactions flagged as statistically large relative to the customer's historical spending patterns.

## Threshold Methodology

The system uses interquartile range (IQR) analysis derived from the customer's own transaction history:

- **Q1**: 25th percentile of historical transaction amounts
- **Q3**: 75th percentile of historical transaction amounts
- **IQR**: Q3 − Q1

**Large Transaction Threshold**: Q3 + 1.5 × IQR (also must be ≥ 3× median)
**Extreme Transaction Threshold**: Q3 + 3 × IQR (also must be ≥ 5× median)

This customer-specific approach prevents false positives: a ₹1,00,000 transaction may be entirely normal for a business account but anomalous for a savings account.

## Investigation Protocol

### Step 1: Context Assessment
Before contacting the customer, review:
- What is the payee category? (business, individual, utility)
- Is this payee previously seen in the customer's history?
- What channel was used? (IMPS/RTGS are more concerning for large amounts than UPI)
- Were there other signals in the same time window?

### Step 2: Legitimate Explanations to Explore
Common benign reasons for large transfers:
- Salary advance or bonus
- Medical expense or hospital payment
- Property purchase down payment
- Loan repayment
- Investment or fixed deposit
- Business payment

### Step 3: Escalation Criteria
Escalate immediately if:
- The amount exceeds the extreme threshold (Q3 + 3×IQR)
- The payee is new (combines with R2)
- The transaction occurred at unusual hours (combines with R3)
- Customer denies knowledge of the transaction

### Step 4: Documentation
Record:
- Customer's stated reason for the transfer
- Any supporting documents provided (invoice, agreement)
- Whether the payee details match the customer's stated purpose
- Outcome of the investigation

## Important Reminders

- Never characterize the transaction as "fraudulent" without explicit customer denial
- Amounts that are unusual are not inherently illegal
- The threshold is statistical, not regulatory — investigator judgment is essential
- Large salary credits or investment maturity proceeds may appear as unusual transfers
