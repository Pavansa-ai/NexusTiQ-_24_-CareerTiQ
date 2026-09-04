"""
Tests for the baseline calculation module.
"""
import pytest
from datetime import datetime, timedelta
from src.core.baseline import compute_baseline, split_historical_current
from src.models.transaction import BaselineConfidence, Transaction


def make_txn(
    tid: str,
    days_ago: int,
    amount: float,
    payee: str = "TestPayee",
    channel: str = "UPI",
    hour: int = 10,
) -> Transaction:
    ts = datetime.now() - timedelta(days=days_ago)
    ts = ts.replace(hour=hour, minute=0, second=0, microsecond=0)
    return Transaction(
        transaction_id=tid,
        timestamp=ts,
        description="Test",
        payee=payee,
        amount=amount,
        channel=channel,
    )


def make_history(n: int = 40, add_current_anchor: bool = True) -> list[Transaction]:
    """
    Create n transactions 31–(31+n) days ago.
    Include an anchor transaction from today so latest_ts ≈ now,
    which makes all 31+ day-old transactions correctly classified as historical.
    """
    txns = []
    if add_current_anchor:
        txns.append(make_txn("ANCHOR_TODAY", 0, 1000.0))
    for i in range(n):
        days_ago = 31 + i  # all at least 31 days ago → historical
        txns.append(make_txn(f"H{i:03d}", days_ago, 1000 + i * 10, hour=10))
    return txns


class TestBaseline:
    def test_high_confidence_requires_30_historical(self):
        txns = make_history(35)  # 35 historical + 1 anchor (current)
        baseline = compute_baseline(txns)
        assert baseline.confidence == BaselineConfidence.HIGH
        assert baseline.n_historical >= 30

    def test_medium_confidence_15_to_29(self):
        txns = make_history(20)  # 20 historical + 1 anchor
        baseline = compute_baseline(txns)
        assert baseline.confidence == BaselineConfidence.MEDIUM

    def test_low_confidence_below_15(self):
        txns = make_history(8)  # 8 historical + 1 anchor
        baseline = compute_baseline(txns)
        assert baseline.confidence == BaselineConfidence.LOW

    def test_insufficient_confidence_below_5(self):
        # Only 3 historical + 1 current → 3 historical → INSUFFICIENT
        txns = [make_txn(f"T{i}", 40 + i, 1000) for i in range(3)]
        txns.append(make_txn("NOW", 0, 1000))  # anchor
        baseline = compute_baseline(txns)
        assert baseline.confidence == BaselineConfidence.INSUFFICIENT

    def test_median_calculated_correctly(self):
        # Use only 5 transactions, no split needed (all fall into analysis pool)
        amounts = [100, 200, 300, 400, 500]
        txns = [make_txn(f"T{i}", 40 + i, amounts[i]) for i in range(5)]
        baseline = compute_baseline(txns)
        # Falls back to all txns (too few for confident split)
        assert baseline.median_amount == pytest.approx(300.0, rel=0.05)

    def test_thresholds_prevent_meaningless_values(self):
        """With tiny historical amounts, thresholds must still be >= 3*median."""
        txns = [make_txn(f"T{i}", 40 + i, 10.0) for i in range(10)]
        baseline = compute_baseline(txns)
        assert baseline.large_threshold >= 3 * baseline.median_amount
        assert baseline.extreme_threshold >= 5 * baseline.median_amount

    def test_empty_transactions(self):
        baseline = compute_baseline([])
        assert baseline.confidence == BaselineConfidence.INSUFFICIENT
        assert baseline.n_historical == 0

    def test_split_historical_current(self):
        # Historical: 35 txns 32–66 days ago (safely older than 30-day cutoff)
        historical_txns = [make_txn(f"H{i:03d}", 32 + i, 1000.0) for i in range(35)]
        # Current: 5 txns 1–5 days ago
        current_txns = [make_txn(f"C{i}", i + 1, 5000.0) for i in range(5)]
        all_txns = historical_txns + current_txns

        hist, curr = split_historical_current(all_txns)
        assert len(curr) == 5
        assert len(hist) == 35
