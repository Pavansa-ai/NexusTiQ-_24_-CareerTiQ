"""
Tests for the deterministic risk engine (R1–R4).
"""
import pytest
from datetime import datetime, timedelta
from src.core.risk_engine import (
    check_large_amount,
    check_new_payee_burst,
    check_odd_hours,
    check_behavioural_deviation,
)
from src.models.transaction import BaselineConfidence, BaselineStats, Transaction


def make_baseline(
    median: float = 1000.0,
    n_historical: int = 40,
    confidence: BaselineConfidence = BaselineConfidence.HIGH,
    hour_start: int = 8,
    hour_end: int = 21,
    common_payees: list | None = None,
) -> BaselineStats:
    iqr = median * 0.6
    q3 = median * 1.3
    large_thresh = max(q3 + 1.5 * iqr, 3 * median)
    extreme_thresh = max(q3 + 3.0 * iqr, 5 * median)
    return BaselineStats(
        n_historical=n_historical,
        confidence=confidence,
        median_amount=median,
        mean_amount=median,
        q1=median * 0.7,
        q3=q3,
        iqr=iqr,
        mad=median * 0.2,
        large_threshold=large_thresh,
        extreme_threshold=extreme_thresh,
        normal_amount_min=0,
        normal_amount_max=large_thresh,
        common_payees=common_payees or ["Known Payee"],
        normal_channels=["UPI", "DEBIT_CARD"],
        active_hour_start=hour_start,
        active_hour_end=hour_end,
        median_daily_txn_count=2.0,
        analysis_period_days=90,
    )


def make_txn(
    tid: str,
    amount: float,
    days_ago: int = 1,
    hour: int = 10,
    payee: str = "Known Payee",
    channel: str = "UPI",
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


# ===========================================================================
# R1 — Large Amount
# ===========================================================================

class TestLargeAmount:
    def setup_method(self):
        self.baseline = make_baseline(median=1000.0)

    def test_normal_amount_not_flagged(self):
        txn = make_txn("TX001", 1200.0)
        rules = check_large_amount([], self.baseline, [txn])
        assert rules == []

    def test_large_amount_flagged(self):
        # large_thresh = max(1.3k + 0.9k, 3k) = 3000. Payee must be unknown.
        txn = make_txn("TX001", 5000.0, payee="Unknown New Vendor")  # not in common_payees
        rules = check_large_amount([], self.baseline, [txn])
        assert len(rules) == 1
        assert rules[0].rule_id == "R1"
        assert "Unusually Large" in rules[0].name
        assert rules[0].score_contribution == 25

    def test_extreme_amount_flagged(self):
        # extreme_thresh = max(1.3k + 1.8k, 5k) = 5000. Payee must be unknown.
        txn = make_txn("TX001", 8000.0, payee="Brand New Entity")  # not in common_payees
        rules = check_large_amount([], self.baseline, [txn])
        assert len(rules) == 1
        assert "Extreme" in rules[0].name
        assert rules[0].score_contribution == 35

    def test_insufficient_baseline_skips_rule(self):
        baseline = make_baseline(n_historical=2, confidence=BaselineConfidence.INSUFFICIENT)
        txn = make_txn("TX001", 100000.0)
        rules = check_large_amount([], baseline, [txn])
        assert rules == []

    def test_large_but_below_3x_median_not_flagged(self):
        """large_threshold = max(q3+1.5*iqr, 3*median). Both conditions must hold."""
        # median=1000, large_thresh=3000. Amount of 2500 < 3000 → not flagged.
        txn = make_txn("TX001", 2500.0)
        rules = check_large_amount([], self.baseline, [txn])
        assert rules == []


# ===========================================================================
# R2 — New Payee Burst
# ===========================================================================

class TestNewPayeeBurst:
    def setup_method(self):
        self.baseline = make_baseline(median=5000.0)
        self.historical = [make_txn("H1", 1000.0, days_ago=60, payee="Known Payee")]

    def _make_burst(self, n: int, hours_apart: float = 6, payee: str = "New Vendor") -> list[Transaction]:
        txns = []
        base_ts = datetime.now() - timedelta(days=1)
        for i in range(n):
            ts = base_ts + timedelta(hours=i * hours_apart)
            txns.append(Transaction(
                transaction_id=f"B{i:03d}",
                timestamp=ts,
                description="Payment",
                payee=payee,
                amount=20000.0,
                channel="IMPS",
            ))
        return txns

    def test_single_new_payee_not_flagged(self):
        txn = [make_txn("TX001", 10000.0, payee="Brand New Payee")]
        rules = check_new_payee_burst([], self.baseline, self.historical, txn)
        assert rules == []

    def test_two_new_payee_txns_not_flagged(self):
        txns = self._make_burst(2)
        rules = check_new_payee_burst([], self.baseline, self.historical, txns)
        assert rules == []

    def test_three_txns_in_48h_triggers_burst(self):
        # 3 txns × ₹20,000 = ₹60,000 > max(50000, 5×5000=25000)
        txns = self._make_burst(3, hours_apart=12)  # 36h span
        rules = check_new_payee_burst([], self.baseline, self.historical, txns)
        assert len(rules) == 1
        assert rules[0].rule_id == "R2"

    def test_existing_payee_not_flagged(self):
        txns = self._make_burst(5, payee="Known Payee")
        rules = check_new_payee_burst([], self.baseline, self.historical, txns)
        assert rules == []

    def test_burst_outside_time_window_not_flagged(self):
        """3 txns but 60 hours apart — exceeds 48h window → not a burst."""
        txns = self._make_burst(3, hours_apart=60)
        rules = check_new_payee_burst([], self.baseline, self.historical, txns)
        assert rules == []


# ===========================================================================
# R3 — Odd Hours
# ===========================================================================

class TestOddHours:
    def setup_method(self):
        self.baseline = make_baseline(n_historical=30, hour_start=8, hour_end=21)

    def test_normal_hour_not_flagged(self):
        txn = make_txn("TX001", 1000.0, hour=14)  # 2 PM — well inside window
        rules = check_odd_hours([], self.baseline, [txn])
        assert rules == []

    def test_odd_hour_flagged(self):
        txn = make_txn("TX001", 1000.0, hour=2)  # 2 AM — far outside window
        rules = check_odd_hours([], self.baseline, [txn])
        assert len(rules) >= 1
        assert rules[0].rule_id == "R3"

    def test_insufficient_history_skips_rule(self):
        baseline = make_baseline(n_historical=5, hour_start=8, hour_end=21)
        txn = make_txn("TX001", 1000.0, hour=2)
        rules = check_odd_hours([], baseline, [txn])
        assert rules == []

    def test_edge_of_window_with_buffer_not_flagged(self):
        """window=8–21, buffer ±2h → effective 6–23. Hour=6 → just inside."""
        txn = make_txn("TX001", 1000.0, hour=6)
        rules = check_odd_hours([], self.baseline, [txn])
        assert rules == []


# ===========================================================================
# R4 — Behavioural Deviation
# ===========================================================================

class TestBehaviouralDeviation:
    def _make_hist(self, n: int = 30) -> list[Transaction]:
        return [
            make_txn(f"H{i}", 1000.0, days_ago=40 + i, payee="Regular Payee", channel="UPI")
            for i in range(n)
        ]

    def test_consistent_customer_no_deviation(self):
        hist = self._make_hist(30)
        # Use explicit make_baseline helper (HIGH confidence) to avoid INSUFFICIENT fallback
        baseline = make_baseline(median=1000.0, n_historical=30)
        current = [
            make_txn(f"C{i}", 1000.0, days_ago=i + 1, payee="Regular Payee", channel="UPI")
            for i in range(5)
        ]
        rule, breakdown = check_behavioural_deviation(hist + current, baseline, hist, current)
        if rule:
            assert breakdown.overall_score < 50

    def test_amount_deviation_triggers(self):
        hist = self._make_hist(30)
        baseline = make_baseline(median=1000.0, n_historical=30)
        # 15× amount deviation
        current = [
            make_txn(f"C{i}", 15000.0, days_ago=i + 1, payee="Regular Payee", channel="UPI")
            for i in range(5)
        ]
        rule, breakdown = check_behavioural_deviation(hist + current, baseline, hist, current)
        assert breakdown is not None
        assert breakdown.amount_score > 30

    def test_all_new_payees_triggers_high_payee_score(self):
        hist = self._make_hist(30)
        baseline = make_baseline(median=1000.0, n_historical=30)
        current = [
            make_txn(f"C{i}", 1000.0, days_ago=i + 1, payee=f"Brand New {i}", channel="UPI")
            for i in range(5)
        ]
        rule, breakdown = check_behavioural_deviation(hist + current, baseline, hist, current)
        assert breakdown is not None
        assert breakdown.payee_score > 50
