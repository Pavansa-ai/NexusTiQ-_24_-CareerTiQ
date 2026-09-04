# Timing Deviation Investigation Policy

## Purpose

This policy guides investigators when transactions are detected outside the customer's established active hours.

## Baseline Determination

The system analyzes the customer's historical transaction timestamps to compute their personal active-hour window:
- Uses the 5th–95th percentile of historical transaction hours
- Extends the window by ±2 hours as a buffer to avoid false positives
- Requires a minimum of 10 historical transactions to apply the rule

**The active window is entirely customer-specific.** A customer who regularly transacts at 11 PM is not flagged for transactions at 11 PM.

## Why Timing Matters

Unusual transaction timing is a recognized risk signal because:
- Account takeover attackers often operate in the victim's off-hours when the account owner is asleep
- Automated fraudulent scripts may operate at predictable off-peak hours to avoid detection
- Victims of social engineering may be coerced to transact urgently at unusual times

However, legitimate reasons also exist: travel across time zones, medical emergencies, irregular work schedules.

## Severity Assessment

The system calculates the deviation in hours from the nearest edge of the buffered active window:
- **Mild deviation** (1–2 hours outside window): Low additional concern
- **Significant deviation** (2–4 hours outside window): Warrants note
- **Strong deviation** (≥4 hours outside window): Warrants investigation, especially if combined with other signals

## Investigation Steps

### Context Assessment
Before contacting the customer:
- Is this an isolated odd-hours transaction, or part of a burst (R2)?
- Was there a large amount involved (R1)?
- Did the channel change?
- Are there other transactions immediately before/after suggesting normal activity?

### Customer Contact
Confirm whether the customer:
- Was awake and aware during the unusual-hours transaction
- Was travelling or in a different time zone
- Recalls receiving any unexpected prompts or calls before the transaction

### Do Not Assume
- Late-night UPI grocery orders (Swiggy/Zomato) are common in urban India — context matters
- The rule provides a signal, not a conclusion
- A single odd-hours transaction without other corroborating signals requires only minimal follow-up

### When to Escalate
Escalate if:
- Customer denies initiating the transaction
- Transaction was to a new payee in a burst (combined R2+R3)
- Multiple odd-hours transactions cluster together
- The amount was also anomalous (combined R1+R3)
