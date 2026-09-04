"""
Deterministic risk engine — implements the four investigation rules.

R1 — Unusually Large Transfer
R2 — New Payee Burst
R3 — Odd-Hours Activity
R4 — Behavioural Pattern Deviation

All logic is independent of Gemini.  These functions compute factual findings.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import numpy as np

from src.core.baseline import split_historical_current
from src.models.transaction import (
    BaselineConfidence,
    BaselineStats,
    PatternDeviationBreakdown,
    RuleId,
    Transaction,
    TriggeredRule,
)

# ---------------------------------------------------------------------------
# Severity labels
# ---------------------------------------------------------------------------

SEVERITY_MILD = "MILD"
SEVERITY_SIGNIFICANT = "SIGNIFICANT"
SEVERITY_STRONG = "STRONG"
SEVERITY_EXTREME = "EXTREME"

# Odd-hours buffer (±2 h around baseline window)
ODD_HOURS_BUFFER = 2


# ===========================================================================
# R1 — Unusually Large Transfer
# ===========================================================================

def check_large_amount(
    transactions: list[Transaction],
    baseline: BaselineStats,
    current_txns: list[Transaction],
) -> list[TriggeredRule]:
    """
    Flag transactions whose amount crosses the large or extreme threshold.
    Only apply rule when baseline confidence is not INSUFFICIENT.
    """
    if baseline.confidence == BaselineConfidence.INSUFFICIENT:
        return []

    # Known payees (historically established) — recurring large amounts like salary/rent
    # should NOT be flagged as suspicious large transfers.
    known_payees_upper = {p.upper() for p in baseline.common_payees}

    rules: list[TriggeredRule] = []

    for txn in current_txns:
        # Skip if this payee is well-established in the customer's history
        if txn.payee.upper() in known_payees_upper:
            continue

        is_extreme = (
            txn.amount > baseline.extreme_threshold
            and txn.amount >= 5 * baseline.median_amount
        )
        is_large = (
            txn.amount > baseline.large_threshold
            and txn.amount >= 3 * baseline.median_amount
        )

        if is_extreme:
            rules.append(TriggeredRule(
                rule_id=RuleId.R1_LARGE_AMOUNT,
                name="Extreme Amount Deviation",
                severity=SEVERITY_EXTREME,
                reason=(
                    f"Transaction {txn.transaction_id} amount ₹{txn.amount:,.0f} "
                    f"exceeds extreme threshold ₹{baseline.extreme_threshold:,.0f} "
                    f"(Q3 + 3×IQR) and is {txn.amount/baseline.median_amount:.1f}× "
                    f"the historical median of ₹{baseline.median_amount:,.0f}. "
                    f"Payee '{txn.payee}' has no prior history with this customer."
                ),
                transaction_ids=[txn.transaction_id],
                score_contribution=35,
            ))
        elif is_large:
            rules.append(TriggeredRule(
                rule_id=RuleId.R1_LARGE_AMOUNT,
                name="Unusually Large Transaction",
                severity=SEVERITY_SIGNIFICANT,
                reason=(
                    f"Transaction {txn.transaction_id} amount ₹{txn.amount:,.0f} "
                    f"exceeds large threshold ₹{baseline.large_threshold:,.0f} "
                    f"(Q3 + 1.5×IQR) and is {txn.amount/baseline.median_amount:.1f}× "
                    f"the historical median of ₹{baseline.median_amount:,.0f}. "
                    f"Payee '{txn.payee}' has no prior history with this customer."
                ),
                transaction_ids=[txn.transaction_id],
                score_contribution=25,
            ))

    return rules


# ===========================================================================
# R2 — New Payee Burst
# ===========================================================================

def check_new_payee_burst(
    transactions: list[Transaction],
    baseline: BaselineStats,
    historical: list[Transaction],
    current_txns: list[Transaction],
) -> list[TriggeredRule]:
    """
    Flag bursts of multiple transactions to a payee not seen in history.
    A single new-payee transaction is NOT flagged — only bursts.
    """
    historical_payees: set[str] = {t.payee.upper() for t in historical}

    # Group current transactions by payee
    payee_groups: dict[str, list[Transaction]] = {}
    for txn in current_txns:
        key = txn.payee.upper()
        payee_groups.setdefault(key, []).append(txn)

    rules: list[TriggeredRule] = []

    for payee_key, group in payee_groups.items():
        # Must be a new payee
        if payee_key in historical_payees or payee_key in ("UNKNOWN", ""):
            continue

        if len(group) < 3:
            continue  # Not a burst

        group_sorted = sorted(group, key=lambda t: t.timestamp)

        # Slide a window to find the densest burst
        burst_rule = _find_best_burst(group_sorted, baseline, payee_key)
        if burst_rule:
            rules.append(burst_rule)

    return rules


def _find_best_burst(
    group: list[Transaction],
    baseline: BaselineStats,
    payee_key: str,
) -> Optional[TriggeredRule]:
    """Find the best burst window within the group."""
    median = baseline.median_amount or 1.0
    best: Optional[TriggeredRule] = None
    best_score = 0

    n = len(group)
    for start_i in range(n):
        for end_i in range(start_i + 2, n):
            window = group[start_i : end_i + 1]
            span_hours = (window[-1].timestamp - window[0].timestamp).total_seconds() / 3600
            total_amt = sum(t.amount for t in window)
            count = len(window)

            # Very strong burst
            if (
                count >= 4
                and span_hours <= 24
                and total_amt >= max(200_000, 15 * median)
            ):
                score = 40
                severity = SEVERITY_EXTREME
            # Strong burst
            elif (
                count >= 3
                and span_hours <= 24
                and total_amt >= max(100_000, 10 * median)
            ):
                score = 30
                severity = SEVERITY_STRONG
            # Baseline burst
            elif (
                count >= 3
                and span_hours <= 48
                and total_amt >= max(50_000, 5 * median)
            ):
                score = 20
                severity = SEVERITY_SIGNIFICANT
            else:
                continue

            if score > best_score:
                best_score = score
                best = TriggeredRule(
                    rule_id=RuleId.R2_NEW_PAYEE_BURST,
                    name="New Payee Burst",
                    severity=severity,
                    reason=(
                        f"{count} transactions to new payee '{group[0].payee}' "
                        f"within {span_hours:.1f} hours totalling ₹{total_amt:,.0f}. "
                        f"This payee has not appeared in the customer's historical records."
                    ),
                    transaction_ids=[t.transaction_id for t in window],
                    score_contribution=score,
                )

    return best


# ===========================================================================
# R3 — Odd-Hours Activity
# ===========================================================================

def check_odd_hours(
    transactions: list[Transaction],
    baseline: BaselineStats,
    current_txns: list[Transaction],
) -> list[TriggeredRule]:
    """
    Flag transactions outside the customer's historical active-hour window.
    Only aggressive when baseline confidence >= MEDIUM and >=10 historical.
    """
    if baseline.n_historical < 10:
        return []

    hour_start = baseline.active_hour_start
    hour_end = baseline.active_hour_end

    # Apply buffer
    window_start = max(0, hour_start - ODD_HOURS_BUFFER)
    window_end = min(23, hour_end + ODD_HOURS_BUFFER)

    odd_txns: list[Transaction] = []
    for txn in current_txns:
        h = txn.timestamp.hour
        if not (window_start <= h <= window_end):
            odd_txns.append(txn)

    if not odd_txns:
        return []

    # Score based on severity of deviation
    rules: list[TriggeredRule] = []
    for txn in odd_txns:
        h = txn.timestamp.hour
        deviation = min(
            abs(h - window_start),
            abs(h - window_end),
            abs(h - window_start + 24),  # wrap-around
        )

        if deviation >= 4:
            severity = SEVERITY_STRONG
        elif deviation >= 2:
            severity = SEVERITY_SIGNIFICANT
        else:
            severity = SEVERITY_MILD

        rules.append(TriggeredRule(
            rule_id=RuleId.R3_ODD_HOURS,
            name="Odd-Hours Activity",
            severity=severity,
            reason=(
                f"Transaction {txn.transaction_id} at {txn.timestamp.strftime('%H:%M')} "
                f"is outside the customer's established activity window "
                f"{hour_start:02d}:00–{hour_end:02d}:00 "
                f"(extended by ±{ODD_HOURS_BUFFER}h buffer: {window_start:02d}:00–{window_end:02d}:00). "
                f"Hour deviation: ~{deviation}h."
            ),
            transaction_ids=[txn.transaction_id],
            score_contribution=15,
        ))

    # De-duplicate: only emit one R3 rule per unique hour-of-day bucket to avoid score inflation
    # Group by hour bucket and keep strongest
    seen_hours: set[int] = set()
    deduplicated: list[TriggeredRule] = []
    for rule in sorted(rules, key=lambda r: r.score_contribution, reverse=True):
        txn_id = rule.transaction_ids[0]
        txn_hour = next(t.timestamp.hour for t in current_txns if t.transaction_id == txn_id)
        bucket = txn_hour // 3  # 3-hour buckets
        if bucket not in seen_hours:
            seen_hours.add(bucket)
            deduplicated.append(rule)

    return deduplicated


# ===========================================================================
# R4 — Behavioural Pattern Deviation
# ===========================================================================

PATTERN_WEIGHTS = {
    "amount": 0.40,
    "time": 0.20,
    "payee": 0.20,
    "channel": 0.10,
    "frequency": 0.10,
}

DEVIATION_THRESHOLDS = {
    "normal": 30,
    "mild": 50,
    "significant": 70,
}


def check_behavioural_deviation(
    transactions: list[Transaction],
    baseline: BaselineStats,
    historical: list[Transaction],
    current_txns: list[Transaction],
) -> tuple[Optional[TriggeredRule], Optional[PatternDeviationBreakdown]]:
    """
    Compute multidimensional behavioural deviation score.
    Returns a TriggeredRule if threshold exceeded, plus breakdown.
    """
    if baseline.confidence == BaselineConfidence.INSUFFICIENT or not current_txns:
        return None, None

    breakdown = _compute_deviation_breakdown(baseline, historical, current_txns)

    overall = breakdown.overall_score

    if overall >= 70:
        severity = SEVERITY_STRONG
        score_contribution = 30
    elif overall >= 50:
        severity = SEVERITY_SIGNIFICANT
        score_contribution = 20
    else:
        return None, breakdown  # Below threshold — no rule triggered

    rule = TriggeredRule(
        rule_id=RuleId.R4_BEHAVIOURAL_DEVIATION,
        name="Behavioural Pattern Deviation",
        severity=severity,
        reason=(
            f"Overall behavioural deviation score: {overall:.0f}/100. "
            f"Amount: {breakdown.amount_label}, "
            f"Timing: {breakdown.time_label}, "
            f"Payee: {breakdown.payee_label}, "
            f"Channel: {breakdown.channel_label}, "
            f"Frequency: {breakdown.frequency_label}."
        ),
        transaction_ids=[t.transaction_id for t in current_txns],
        score_contribution=score_contribution,
    )
    return rule, breakdown


def _compute_deviation_breakdown(
    baseline: BaselineStats,
    historical: list[Transaction],
    current_txns: list[Transaction],
) -> PatternDeviationBreakdown:
    # -- Amount deviation --
    curr_amounts = [t.amount for t in current_txns]
    curr_median = float(np.median(curr_amounts)) if curr_amounts else 0.0
    if baseline.median_amount > 0:
        amount_ratio = curr_median / baseline.median_amount
        amount_score_raw = min(100.0, abs(amount_ratio - 1.0) * 60)
    else:
        amount_score_raw = 0.0

    # -- Time deviation --
    curr_hours = [t.timestamp.hour for t in current_txns]
    hist_hours = [t.timestamp.hour for t in historical]
    if hist_hours and curr_hours:
        hist_hour_mean = float(np.mean(hist_hours))
        curr_hour_mean = float(np.mean(curr_hours))
        hour_dev = abs(curr_hour_mean - hist_hour_mean)
        time_score_raw = min(100.0, hour_dev * 10)
    else:
        time_score_raw = 0.0

    # -- Payee deviation --
    hist_payees = {t.payee.upper() for t in historical}
    curr_payees = {t.payee.upper() for t in current_txns}
    if curr_payees and hist_payees:
        new_payee_fraction = len(curr_payees - hist_payees) / len(curr_payees)
        payee_score_raw = min(100.0, new_payee_fraction * 120)
    elif curr_payees:
        payee_score_raw = 70.0
    else:
        payee_score_raw = 0.0

    # -- Channel deviation --
    hist_channels = {t.channel.upper() for t in historical}
    curr_channels_list = [t.channel.upper() for t in current_txns]
    if curr_channels_list and hist_channels:
        unusual_channel_count = sum(1 for c in curr_channels_list if c not in hist_channels)
        channel_score_raw = min(100.0, (unusual_channel_count / len(curr_channels_list)) * 100)
    else:
        channel_score_raw = 0.0

    # -- Frequency deviation --
    if baseline.median_daily_txn_count > 0 and baseline.analysis_period_days > 0:
        curr_days = max(
            1,
            (
                max(t.timestamp for t in current_txns)
                - min(t.timestamp for t in current_txns)
            ).days + 1,
        )
        curr_daily = len(current_txns) / curr_days
        freq_ratio = curr_daily / baseline.median_daily_txn_count
        frequency_score_raw = min(100.0, abs(freq_ratio - 1.0) * 50)
    else:
        frequency_score_raw = 0.0

    # -- Weighted overall --
    overall = (
        PATTERN_WEIGHTS["amount"] * amount_score_raw
        + PATTERN_WEIGHTS["time"] * time_score_raw
        + PATTERN_WEIGHTS["payee"] * payee_score_raw
        + PATTERN_WEIGHTS["channel"] * channel_score_raw
        + PATTERN_WEIGHTS["frequency"] * frequency_score_raw
    )

    def label(score: float) -> str:
        if score < 30:
            return "Normal"
        elif score < 50:
            return "Mild deviation"
        elif score < 70:
            return "Moderate deviation"
        else:
            return "Strong deviation"

    return PatternDeviationBreakdown(
        amount_score=round(amount_score_raw, 1),
        time_score=round(time_score_raw, 1),
        payee_score=round(payee_score_raw, 1),
        channel_score=round(channel_score_raw, 1),
        frequency_score=round(frequency_score_raw, 1),
        overall_score=round(overall, 1),
        amount_label=label(amount_score_raw),
        time_label=label(time_score_raw),
        payee_label=label(payee_score_raw),
        channel_label=label(channel_score_raw),
        frequency_label=label(frequency_score_raw),
    )
