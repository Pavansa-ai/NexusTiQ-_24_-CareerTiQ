"""
Verified Evidence Object builder.

Assembles the compact, deterministic evidence package that is passed to Gemini.
Only relevant, verified data is included.  The full transaction history is NOT sent.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional

from src.core.baseline import split_historical_current
from src.core.clustering import build_clusters
from src.core.risk_engine import (
    check_behavioural_deviation,
    check_large_amount,
    check_new_payee_burst,
    check_odd_hours,
)
from src.core.scoring import (
    compute_priority_score,
    determine_investigation_status,
    get_risk_level,
)
from src.models.transaction import (
    BaselineStats,
    FlaggedTransaction,
    InvestigationStatus,
    PatternDeviationBreakdown,
    Transaction,
    TransactionCluster,
    TriggeredRule,
    VerifiedEvidence,
)


def build_evidence(
    transactions: list[Transaction],
    baseline: BaselineStats,
    customer_name: str = "Customer",
) -> tuple[VerifiedEvidence, Optional[PatternDeviationBreakdown]]:
    """
    Run all deterministic checks and assemble the VerifiedEvidence object.
    Returns (evidence, pattern_breakdown).
    """
    historical, current = split_historical_current(transactions)

    # Fall back: if no historical data, use all transactions as pool
    if not historical:
        historical = transactions
    if not current:
        current = transactions

    # ----- Run risk rules -----------------------------------------------
    r1_rules = check_large_amount(transactions, baseline, current)
    r2_rules = check_new_payee_burst(transactions, baseline, historical, current)
    r3_rules = check_odd_hours(transactions, baseline, current)
    r4_rule, pattern_breakdown = check_behavioural_deviation(
        transactions, baseline, historical, current
    )

    all_rules: list[TriggeredRule] = r1_rules + r2_rules + r3_rules
    if r4_rule:
        all_rules.append(r4_rule)

    # ----- Scoring -------------------------------------------------------
    priority_score = compute_priority_score(all_rules)
    risk_level = get_risk_level(priority_score)
    investigation_status = determine_investigation_status(priority_score, all_rules)

    # ----- Collect flagged transaction IDs ------------------------------
    flagged_ids: set[str] = set()
    for rule in all_rules:
        flagged_ids.update(rule.transaction_ids)

    txn_map = {t.transaction_id: t for t in transactions}
    flagged_txns_raw = [txn_map[tid] for tid in flagged_ids if tid in txn_map]
    flagged_txns_raw.sort(key=lambda t: t.timestamp)

    # Map each flagged txn to its rules
    txn_rule_map: dict[str, list[str]] = {}
    cluster_map_txn: dict[str, str] = {}  # txn_id → cluster_id (filled after clustering)

    for rule in all_rules:
        for tid in rule.transaction_ids:
            txn_rule_map.setdefault(tid, [])
            if rule.rule_id not in txn_rule_map[tid]:
                txn_rule_map[tid].append(rule.rule_id)

    # ----- Cluster flagged transactions ----------------------------------
    clusters = build_clusters(flagged_txns_raw, transactions, all_rules)

    for cluster in clusters:
        for tid in cluster.transaction_ids:
            cluster_map_txn[tid] = cluster.cluster_id

    # ----- Build compact FlaggedTransaction list ------------------------
    flagged_transactions: list[FlaggedTransaction] = []
    for txn in flagged_txns_raw:
        flagged_transactions.append(
            FlaggedTransaction(
                transaction_id=txn.transaction_id,
                timestamp=txn.timestamp.isoformat(),
                description=txn.description,
                payee=txn.payee,
                amount=txn.amount,
                channel=txn.channel,
                triggered_rules=txn_rule_map.get(txn.transaction_id, []),
                cluster_id=cluster_map_txn.get(txn.transaction_id),
            )
        )

    # ----- Baseline summary (compact) -----------------------------------
    baseline_summary = {
        "median_amount": round(baseline.median_amount, 2),
        "mean_amount": round(baseline.mean_amount, 2),
        "q1": round(baseline.q1, 2),
        "q3": round(baseline.q3, 2),
        "iqr": round(baseline.iqr, 2),
        "large_threshold": round(baseline.large_threshold, 2),
        "extreme_threshold": round(baseline.extreme_threshold, 2),
        "normal_activity_window": f"{baseline.active_hour_start:02d}:00–{baseline.active_hour_end:02d}:00",
        "common_payees_sample": baseline.common_payees[:8],
        "normal_channels": baseline.normal_channels,
        "n_historical": baseline.n_historical,
        "confidence": baseline.confidence.value,
    }

    # ----- Deviations summary -------------------------------------------
    deviations: dict[str, str] = {}
    if pattern_breakdown:
        deviations = {
            "amount": pattern_breakdown.amount_label,
            "time": pattern_breakdown.time_label,
            "payee": pattern_breakdown.payee_label,
            "channel": pattern_breakdown.channel_label,
            "frequency": pattern_breakdown.frequency_label,
            "overall_score": str(pattern_breakdown.overall_score),
        }

    # ----- Analysis period ---------------------------------------------
    if transactions:
        ts_min = min(t.timestamp for t in transactions)
        ts_max = max(t.timestamp for t in transactions)
        analysis_period = f"{ts_min.strftime('%d %b %Y')} – {ts_max.strftime('%d %b %Y')}"
    else:
        analysis_period = "N/A"

    # ----- Build evidence object ----------------------------------------
    evidence = VerifiedEvidence(
        investigation_status=investigation_status,
        priority_score=priority_score,
        priority_level=risk_level,
        baseline_confidence=baseline.confidence,
        triggered_rules=all_rules,
        flagged_transactions=flagged_transactions,
        clusters=clusters,
        baseline=baseline_summary,
        deviations=deviations,
        customer_name=customer_name,
        analysis_period=analysis_period,
        total_transactions=len(transactions),
    )

    # ----- Evidence hash (for caching) ----------------------------------
    evidence.evidence_hash = _compute_hash(evidence)

    return evidence, pattern_breakdown


def _compute_hash(evidence: VerifiedEvidence) -> str:
    """SHA-256 hash of the evidence for cache keying."""
    payload = {
        "status": evidence.investigation_status.value,
        "score": evidence.priority_score,
        "rules": [
            {"id": r.rule_id, "txns": sorted(r.transaction_ids)}
            for r in sorted(evidence.triggered_rules, key=lambda r: r.rule_id)
        ],
        "flagged_ids": sorted(f.transaction_id for f in evidence.flagged_transactions),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()[:32]
