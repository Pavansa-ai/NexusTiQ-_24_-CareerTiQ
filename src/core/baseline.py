"""
Customer baseline calculation from historical transaction data.

Historical baseline = transactions older than the most recent 30 days.
Current activity = transactions in the most recent 30 days.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from src.models.transaction import BaselineConfidence, BaselineStats, Transaction

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HISTORICAL_WINDOW_DAYS = 30  # days before the cutoff that define "history"
HIGH_CONFIDENCE_MIN = 30     # >= 30 historical txns → HIGH confidence
MEDIUM_CONFIDENCE_MIN = 15   # 15–29 → MEDIUM
# <15 → LOW
# <5  → INSUFFICIENT

DEFAULT_HOUR_START = 8
DEFAULT_HOUR_END = 22


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def compute_baseline(transactions: list[Transaction]) -> BaselineStats:
    """
    Compute customer behavioural baseline from historical transactions.
    'Historical' = transactions older than the most-recent 30 days.
    """
    if not transactions:
        return _empty_baseline()

    # Determine cutoff: most recent timestamp minus 30 days
    latest_ts = max(t.timestamp for t in transactions)
    cutoff = latest_ts - timedelta(days=HISTORICAL_WINDOW_DAYS)

    historical = [t for t in transactions if t.timestamp < cutoff]
    current = [t for t in transactions if t.timestamp >= cutoff]

    n_historical = len(historical)

    # Confidence
    if n_historical >= HIGH_CONFIDENCE_MIN:
        confidence = BaselineConfidence.HIGH
    elif n_historical >= MEDIUM_CONFIDENCE_MIN:
        confidence = BaselineConfidence.MEDIUM
    elif n_historical >= 5:
        confidence = BaselineConfidence.LOW
    else:
        confidence = BaselineConfidence.INSUFFICIENT

    # Use available data even if sparse — fall back to all transactions if history is tiny
    analysis_pool = historical if n_historical >= 5 else transactions

    amounts = [t.amount for t in analysis_pool]
    timestamps_hist = [t.timestamp for t in analysis_pool]

    # Amount statistics
    median_amt = float(np.median(amounts))
    mean_amt = float(np.mean(amounts))
    q1 = float(np.percentile(amounts, 25))
    q3 = float(np.percentile(amounts, 75))
    iqr = q3 - q1
    mad = float(_median_absolute_deviation(amounts))

    large_threshold = q3 + 1.5 * iqr
    extreme_threshold = q3 + 3.0 * iqr

    # Prevent meaninglessly low thresholds
    large_threshold = max(large_threshold, 3 * median_amt)
    extreme_threshold = max(extreme_threshold, 5 * median_amt)

    normal_min = max(0.0, q1 - 1.5 * iqr)
    normal_max = large_threshold

    # Common payees (appear in >= 2 historical transactions OR top-10)
    payee_counts: dict[str, int] = {}
    for t in analysis_pool:
        payee_counts[t.payee] = payee_counts.get(t.payee, 0) + 1
    common_payees = sorted(payee_counts, key=payee_counts.get, reverse=True)[:20]

    # Common channels
    channel_counts: dict[str, int] = {}
    for t in analysis_pool:
        channel_counts[t.channel] = channel_counts.get(t.channel, 0) + 1
    normal_channels = [c for c, cnt in sorted(channel_counts.items(), key=lambda x: -x[1])
                       if cnt >= max(1, len(analysis_pool) * 0.05)]

    # Active hours
    hours = [ts.hour for ts in timestamps_hist]
    hour_start, hour_end = _compute_active_window(hours)

    # Transaction frequency (daily)
    if len(analysis_pool) >= 2:
        date_range = (max(timestamps_hist) - min(timestamps_hist)).days or 1
        median_daily = len(analysis_pool) / max(date_range, 1)
    else:
        median_daily = 1.0

    # Analysis period
    all_timestamps = [t.timestamp for t in transactions]
    period_days = (max(all_timestamps) - min(all_timestamps)).days + 1

    return BaselineStats(
        n_historical=n_historical,
        confidence=confidence,
        median_amount=median_amt,
        mean_amount=mean_amt,
        q1=q1,
        q3=q3,
        iqr=iqr,
        mad=mad,
        large_threshold=large_threshold,
        extreme_threshold=extreme_threshold,
        normal_amount_min=normal_min,
        normal_amount_max=normal_max,
        common_payees=common_payees,
        normal_channels=normal_channels,
        active_hour_start=hour_start,
        active_hour_end=hour_end,
        median_daily_txn_count=median_daily,
        analysis_period_days=period_days,
    )


def split_historical_current(
    transactions: list[Transaction],
) -> tuple[list[Transaction], list[Transaction]]:
    """
    Return (historical, current) lists using the 30-day cutoff.
    Historical = older than cutoff; Current = within last 30 days.
    """
    if not transactions:
        return [], []
    latest_ts = max(t.timestamp for t in transactions)
    cutoff = latest_ts - timedelta(days=HISTORICAL_WINDOW_DAYS)
    historical = [t for t in transactions if t.timestamp < cutoff]
    current = [t for t in transactions if t.timestamp >= cutoff]
    return historical, current


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    med = float(np.median(values))
    return float(np.median([abs(v - med) for v in values]))


def _compute_active_window(hours: list[int]) -> tuple[int, int]:
    """
    Find the hour window that covers ~90% of historical activity.
    Falls back to 08–22 if insufficient data.
    """
    if len(hours) < 5:
        return DEFAULT_HOUR_START, DEFAULT_HOUR_END

    # Compute percentile-based window
    h_arr = np.array(hours)
    p5 = int(np.percentile(h_arr, 5))
    p95 = int(np.percentile(h_arr, 95))

    # Sanity: if everything is at same hour, give ±2 buffer
    if p5 == p95:
        return max(0, p5 - 2), min(23, p95 + 2)

    return p5, p95


def _empty_baseline() -> BaselineStats:
    return BaselineStats(
        n_historical=0,
        confidence=BaselineConfidence.INSUFFICIENT,
        median_amount=0.0,
        mean_amount=0.0,
        q1=0.0,
        q3=0.0,
        iqr=0.0,
        mad=0.0,
        large_threshold=float("inf"),
        extreme_threshold=float("inf"),
        normal_amount_min=0.0,
        normal_amount_max=float("inf"),
        common_payees=[],
        normal_channels=[],
        active_hour_start=DEFAULT_HOUR_START,
        active_hour_end=DEFAULT_HOUR_END,
        median_daily_txn_count=0.0,
        analysis_period_days=0,
    )
