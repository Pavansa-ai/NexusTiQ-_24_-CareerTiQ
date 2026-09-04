# Investigation Rules Reference

## Overview

This document describes the four deterministic investigation rules used by the Banking Transaction Risk Investigation Assistant. These rules are applied to every transaction history to identify signals that warrant investigator attention.

## Rule R1 — Unusually Large Transfer

### Purpose
Identify transactions whose amount is statistically anomalous relative to the customer's own historical spending baseline.

### Trigger Conditions
A transaction triggers R1 if:

**Large Transaction:**
- Amount > Q3 + 1.5 × IQR (customer's historical distribution)
- AND Amount ≥ 3 × historical median

**Extreme Transaction:**
- Amount > Q3 + 3 × IQR
- AND Amount ≥ 5 × historical median

### Score Contributions
- Large transaction: +25 Investigation Priority points
- Extreme transaction: +35 Investigation Priority points

### Important Notes
- The threshold is customer-specific, not a fixed rupee amount
- A ₹50,000 transaction may be normal for one customer and extreme for another
- This rule should NOT be interpreted as evidence of fraud
- A legitimate explanation (salary advance, medical emergency, property purchase) must be excluded

## Rule R2 — New Payee Burst

### Purpose
Identify rapid, repeated fund transfers to a payee that has never appeared in the customer's historical records.

### Definition of "New Payee"
A payee is considered new when their historical transaction count = 0.

### Trigger Conditions
**Baseline Burst:**
- Payee is new
- ≥ 3 transactions to this payee
- Within 48 hours
- Total cluster amount ≥ max(₹50,000, 5 × customer median)

**Strong Burst:**
- ≥ 3 transactions within 24 hours
- Total ≥ max(₹1,00,000, 10 × median)

**Very Strong Burst:**
- ≥ 4 transactions within 24 hours
- Total ≥ max(₹2,00,000, 15 × median)

### Score Contributions
- Baseline burst: +20 points
- Strong burst: +30 points
- Very strong burst: +40 points

### Important Notes
- A single transaction to a new payee does NOT trigger this rule
- The rule scores the cluster as a whole, not each transaction individually
- Multiple channel types within the burst increase investigator concern

## Rule R3 — Odd-Hours Activity

### Purpose
Detect transactions occurring outside the customer's established active hours.

### How Active Hours Are Determined
The system computes the 5th–95th percentile of the customer's historical transaction hours. This window is then extended by ±2 hours as a buffer.

### Trigger Conditions
- Transaction hour falls outside the buffered active window
- ≥ 10 historical transactions required (insufficient data → rule skipped)

### Score Contribution
- Odd-hours transaction: +15 points

### Important Notes
- "Odd hours" is defined relative to the individual customer, not a universal standard
- A customer who habitually transacts at night would NOT be flagged for night transactions
- This rule carries more weight when combined with other signals (R2, R1)

## Rule R4 — Behavioural Pattern Deviation

### Purpose
Detect multidimensional deviations from the customer's established behaviour, even when individual transactions appear normal.

### Dimensions
| Dimension | Weight |
|-----------|--------|
| Amount    | 40%    |
| Timing    | 20%    |
| Payee     | 20%    |
| Channel   | 10%    |
| Frequency | 10%    |

### Score Mapping
- 0–29: Normal behaviour
- 30–49: Mild deviation (not flagged)
- 50–69: Significant deviation → +20 points
- 70–100: Strong deviation → +30 points

### Important Notes
- This rule should always be explained in terms of specific dimensional scores
- Do not simply display a number — explain which dimensions deviated and by how much
- This rule is particularly powerful when multiple dimensions show concurrent deviation
