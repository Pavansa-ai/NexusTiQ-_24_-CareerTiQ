"""
Transaction clustering — groups related flagged transactions into clusters.

Clusters represent connected activity based on: payee, time window, channel,
triggered rules, or same-day activity.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from src.models.transaction import Transaction, TransactionCluster, TriggeredRule

CLUSTER_TIME_WINDOW_HOURS = 48  # Max hours between first and last txn in a cluster


def build_clusters(
    flagged_transactions: list[Transaction],
    all_transactions: list[Transaction],
    triggered_rules: list[TriggeredRule],
) -> list[TransactionCluster]:
    """
    Group flagged transactions into meaningful clusters.
    Each cluster has a shared payee, time window, or rule set.
    """
    if not flagged_transactions:
        return []

    # Map transaction_id → rules that flagged it
    txn_rules: dict[str, list[str]] = {}
    for rule in triggered_rules:
        for txn_id in rule.transaction_ids:
            txn_rules.setdefault(txn_id, [])
            if rule.rule_id not in txn_rules[txn_id]:
                txn_rules[txn_id].append(rule.rule_id)

    # Map transaction_id → Transaction object
    txn_map: dict[str, Transaction] = {t.transaction_id: t for t in all_transactions}

    clusters: list[TransactionCluster] = []
    cluster_counter = 1

    # Strategy 1: Cluster by same payee
    payee_groups: dict[str, list[Transaction]] = {}
    for txn in flagged_transactions:
        payee_groups.setdefault(txn.payee.upper(), []).append(txn)

    seen_ids: set[str] = set()

    for payee_key, group in payee_groups.items():
        group_sorted = sorted(group, key=lambda t: t.timestamp)

        # Split group into sub-clusters within the time window
        sub_clusters = _split_by_time_window(group_sorted, CLUSTER_TIME_WINDOW_HOURS)

        for sub in sub_clusters:
            if len(sub) < 1:
                continue

            ids = [t.transaction_id for t in sub]
            # Mark as seen
            for tid in ids:
                seen_ids.add(tid)

            span_hours = (
                (sub[-1].timestamp - sub[0].timestamp).total_seconds() / 3600
                if len(sub) > 1
                else 0.0
            )
            total_amount = sum(t.amount for t in sub)

            # Collect unique rules for this cluster
            cluster_rules: list[str] = []
            for tid in ids:
                for r in txn_rules.get(tid, []):
                    if r not in cluster_rules:
                        cluster_rules.append(r)

            cluster = TransactionCluster(
                cluster_id=f"C{cluster_counter:03d}",
                transaction_ids=ids,
                rules_triggered=cluster_rules,
                total_amount=total_amount,
                time_span_hours=round(span_hours, 1),
                payee=sub[0].payee,
                explanation=_build_cluster_explanation(sub, cluster_rules, total_amount, span_hours),
            )
            clusters.append(cluster)
            cluster_counter += 1

    # Strategy 2: Any remaining flagged transactions not yet clustered
    remaining = [t for t in flagged_transactions if t.transaction_id not in seen_ids]
    if remaining:
        # Group remaining by same-day
        day_groups: dict[str, list[Transaction]] = {}
        for txn in remaining:
            day_key = txn.timestamp.date().isoformat()
            day_groups.setdefault(day_key, []).append(txn)

        for day_key, group in day_groups.items():
            ids = [t.transaction_id for t in group]
            total_amount = sum(t.amount for t in group)
            span_hours = (
                (
                    max(t.timestamp for t in group)
                    - min(t.timestamp for t in group)
                ).total_seconds() / 3600
                if len(group) > 1
                else 0.0
            )
            cluster_rules_set: list[str] = []
            for tid in ids:
                for r in txn_rules.get(tid, []):
                    if r not in cluster_rules_set:
                        cluster_rules_set.append(r)

            cluster = TransactionCluster(
                cluster_id=f"C{cluster_counter:03d}",
                transaction_ids=ids,
                rules_triggered=cluster_rules_set,
                total_amount=total_amount,
                time_span_hours=round(span_hours, 1),
                payee=None,
                explanation=f"Same-day activity on {day_key}: {len(group)} transaction(s) totalling ₹{total_amount:,.0f}.",
            )
            clusters.append(cluster)
            cluster_counter += 1

    return clusters


def _split_by_time_window(
    sorted_txns: list[Transaction], max_hours: float
) -> list[list[Transaction]]:
    """Split a time-sorted group into sub-groups that fit within max_hours."""
    if not sorted_txns:
        return []

    sub_clusters: list[list[Transaction]] = []
    current_sub = [sorted_txns[0]]

    for txn in sorted_txns[1:]:
        span = (txn.timestamp - current_sub[0].timestamp).total_seconds() / 3600
        if span <= max_hours:
            current_sub.append(txn)
        else:
            sub_clusters.append(current_sub)
            current_sub = [txn]

    sub_clusters.append(current_sub)
    return sub_clusters


def _build_cluster_explanation(
    group: list[Transaction],
    rule_ids: list[str],
    total_amount: float,
    span_hours: float,
) -> str:
    payee = group[0].payee
    count = len(group)
    rule_names = {
        "R1": "Amount Deviation",
        "R2": "New Payee Burst",
        "R3": "Odd-Hours Activity",
        "R4": "Behavioural Deviation",
    }
    triggered = [rule_names.get(r, r) for r in rule_ids]
    triggered_str = ", ".join(triggered) if triggered else "None"

    span_str = (
        f"{span_hours:.1f} hours"
        if span_hours >= 1
        else f"{int(span_hours * 60)} minutes"
    )

    return (
        f"{count} transaction(s) to payee '{payee}' "
        f"over {span_str}, "
        f"total ₹{total_amount:,.0f}. "
        f"Triggered: {triggered_str}."
    )
