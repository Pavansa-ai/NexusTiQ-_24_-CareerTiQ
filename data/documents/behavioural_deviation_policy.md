# Behavioural Deviation Investigation Policy

## Purpose

This policy guides investigators when a customer's current transaction pattern shows significant multi-dimensional deviation from their established historical baseline.

## What Is Behavioural Pattern Deviation?

Unlike single-metric rules (amount, timing), behavioural deviation analysis evaluates the current period's activity across five dimensions simultaneously:

| Dimension | Description | Weight |
|-----------|-------------|--------|
| Amount | How much does the current median/distribution differ from historical? | 40% |
| Timing | How much do average transaction hours differ from historical? | 20% |
| Payee | What fraction of current payees are new to this customer's history? | 20% |
| Channel | What fraction of current transactions use channels not seen historically? | 10% |
| Frequency | How much does the daily transaction rate differ from historical? | 10% |

## Score Interpretation

| Score | Label | Action |
|-------|-------|--------|
| 0–29 | Normal | No action required |
| 30–49 | Mild deviation | Note for record only |
| 50–69 | Significant deviation | Secondary review recommended |
| 70–100 | Strong deviation | Full investigation warranted |

## Individual Dimension Labels

Each dimension is labeled independently:
- **Normal**: Score 0–29
- **Mild deviation**: Score 30–49
- **Moderate deviation**: Score 50–69
- **Strong deviation**: Score 70–100

Investigators should always review which dimensions contributed most to the overall score.

## Interpreting Combinations

Certain combinations are particularly significant:

**High payee + high amount deviation:**
Suggests the customer is transacting with unfamiliar parties at unusual amounts — common in account takeover or social engineering attacks.

**High payee + high channel deviation:**
Suggests an unfamiliar actor using the account, potentially with access to specific payment methods.

**High frequency + high amount:**
May indicate someone rapidly liquidating an account.

**Timing + payee deviation:**
New payees contacted at unusual hours — warrants prompt investigation.

## Investigation Steps

1. **Identify the dominant deviation dimension** — which dimension has the highest score?
2. **Cross-reference with triggered rules** — is R4 supporting an R2 or R1 finding?
3. **Review the specific transactions** causing the deviation
4. **Contact the customer** and inquire about the changed behaviour pattern
5. **Document the customer's explanation** and assess plausibility

## Limitations

- Behavioural deviation analysis requires at least 5 historical transactions
- Low baseline confidence weakens the reliability of this rule
- Life events (job change, relocation, new business) legitimately cause behavioural shifts
- The rule provides a signal, not a conclusion
