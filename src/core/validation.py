"""
CSV validation and parsing for transaction data.
Handles missing values, malformed timestamps, duplicates, and edge cases.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

from src.models.transaction import Transaction

# ---------------------------------------------------------------------------
# Column alias mapping — accept common column name variants
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, list[str]] = {
    "transaction_id": ["transaction_id", "txn_id", "id", "tx_id", "trans_id", "txid"],
    "timestamp": ["timestamp", "date", "datetime", "date_time", "time", "transaction_date", "txn_date"],
    "description": ["description", "desc", "narration", "remarks", "memo", "details", "particulars"],
    "payee": ["payee", "beneficiary", "recipient", "to", "party", "counterparty", "vendor", "merchant"],
    "amount": ["amount", "amt", "value", "transaction_amount", "debit", "credit"],
    "channel": ["channel", "mode", "payment_mode", "txn_type", "transaction_type", "type"],
}

REQUIRED_COLUMNS = ["transaction_id", "timestamp", "amount"]

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    transactions: list[Transaction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    is_valid: bool = True
    row_count_raw: int = 0
    row_count_valid: int = 0


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def validate_and_parse(csv_content: str) -> ValidationResult:
    """
    Parse a CSV string and return cleaned Transaction objects.
    Never raises — all issues are captured in ValidationResult.
    """
    result = ValidationResult()

    # -----------------------------------------------------------------------
    # 1. Basic CSV parse
    # -----------------------------------------------------------------------
    if not csv_content or not csv_content.strip():
        result.errors.append("CSV content is empty.")
        result.is_valid = False
        return result

    try:
        df = pd.read_csv(io.StringIO(csv_content.strip()))
    except Exception as exc:
        result.errors.append(f"Could not parse CSV: {exc}")
        result.is_valid = False
        return result

    result.row_count_raw = len(df)

    if df.empty:
        result.errors.append("CSV contains no data rows.")
        result.is_valid = False
        return result

    # -----------------------------------------------------------------------
    # 2. Normalise column names — lowercase + strip
    # -----------------------------------------------------------------------
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    # -----------------------------------------------------------------------
    # 3. Map aliases to canonical column names
    # -----------------------------------------------------------------------
    canonical_map: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns and canonical not in canonical_map:
                canonical_map[alias] = canonical

    df = df.rename(columns=canonical_map)

    # -----------------------------------------------------------------------
    # 4. Check required columns
    # -----------------------------------------------------------------------
    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        result.errors.append(
            f"Missing required column(s): {', '.join(missing_required)}. "
            f"Available columns: {', '.join(df.columns.tolist())}."
        )
        result.is_valid = False
        return result

    # -----------------------------------------------------------------------
    # 5. Fill optional columns with defaults
    # -----------------------------------------------------------------------
    if "description" not in df.columns:
        df["description"] = ""
        result.warnings.append("No 'description' column found; defaulting to empty string.")
    if "payee" not in df.columns:
        df["payee"] = "UNKNOWN"
        result.warnings.append("No 'payee' column found; defaulting to 'UNKNOWN'.")
    if "channel" not in df.columns:
        df["channel"] = "UNKNOWN"
        result.warnings.append("No 'channel' column found; defaulting to 'UNKNOWN'.")

    # -----------------------------------------------------------------------
    # 6. Drop fully duplicate rows
    # -----------------------------------------------------------------------
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        df = df.drop_duplicates()
        result.warnings.append(f"Removed {dup_count} fully duplicate row(s).")

    # -----------------------------------------------------------------------
    # 7. Handle duplicate transaction IDs (keep first, warn)
    # -----------------------------------------------------------------------
    df["transaction_id"] = df["transaction_id"].astype(str).str.strip()
    dup_ids = df[df.duplicated("transaction_id", keep=False)]["transaction_id"].unique()
    if len(dup_ids) > 0:
        result.warnings.append(
            f"Duplicate transaction IDs found (keeping first occurrence): {', '.join(dup_ids[:5])}{'...' if len(dup_ids) > 5 else ''}"
        )
        df = df.drop_duplicates(subset=["transaction_id"], keep="first")

    # -----------------------------------------------------------------------
    # 8. Parse amounts — must be numeric and positive
    # -----------------------------------------------------------------------
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    non_numeric = df["amount"].isna().sum()
    if non_numeric > 0:
        result.warnings.append(f"Dropping {non_numeric} row(s) with non-numeric 'amount'.")
        df = df[df["amount"].notna()]

    zero_neg = (df["amount"] <= 0).sum()
    if zero_neg > 0:
        result.warnings.append(
            f"Dropping {zero_neg} row(s) with zero or negative 'amount' "
            "(only debit transactions are analyzed)."
        )
        df = df[df["amount"] > 0]

    if df.empty:
        result.errors.append("No valid transactions remain after amount filtering.")
        result.is_valid = False
        return result

    # -----------------------------------------------------------------------
    # 9. Parse timestamps
    # -----------------------------------------------------------------------
    df, ts_warnings = _parse_timestamps(df)
    result.warnings.extend(ts_warnings)

    if df.empty:
        result.errors.append("No rows with parseable timestamps remain.")
        result.is_valid = False
        return result

    # -----------------------------------------------------------------------
    # 10. Clean text fields
    # -----------------------------------------------------------------------
    for col in ["description", "payee", "channel"]:
        df[col] = df[col].astype(str).str.strip().fillna("")

    df["payee"] = df["payee"].replace({"": "UNKNOWN", "nan": "UNKNOWN"})
    df["channel"] = df["channel"].replace({"": "UNKNOWN", "nan": "UNKNOWN"}).str.upper()
    df["description"] = df["description"].replace({"nan": ""})

    # -----------------------------------------------------------------------
    # 11. Sort by timestamp ascending
    # -----------------------------------------------------------------------
    df = df.sort_values("timestamp").reset_index(drop=True)

    # -----------------------------------------------------------------------
    # 12. Build Transaction objects
    # -----------------------------------------------------------------------
    transactions: list[Transaction] = []
    for idx, row in df.iterrows():
        try:
            txn = Transaction(
                transaction_id=str(row["transaction_id"]),
                timestamp=row["timestamp"],
                description=str(row.get("description", "")),
                payee=str(row.get("payee", "UNKNOWN")),
                amount=float(row["amount"]),
                channel=str(row.get("channel", "UNKNOWN")),
                row_index=int(idx),
            )
            transactions.append(txn)
        except Exception as exc:
            result.warnings.append(f"Skipping row {idx}: {exc}")

    result.transactions = transactions
    result.row_count_valid = len(transactions)

    if result.row_count_valid == 0:
        result.errors.append("No valid transactions could be parsed.")
        result.is_valid = False
    elif result.row_count_valid < 5:
        result.warnings.append(
            f"Only {result.row_count_valid} valid transaction(s) found. "
            "Analysis will have very limited baseline confidence."
        )

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_timestamps(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Try multiple timestamp formats and return cleaned df + warnings."""
    warnings: list[str] = []

    formats_to_try = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%Y%m%d",
    ]

    # First try pandas generic inference
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    failed_mask = df["timestamp"].isna()

    if failed_mask.any():
        # Try explicit formats on the failed rows
        raw_col = df.loc[failed_mask, "timestamp_raw"] if "timestamp_raw" in df.columns else None
        for fmt in formats_to_try:
            still_failed = df["timestamp"].isna()
            if not still_failed.any():
                break
            try:
                fixed = pd.to_datetime(df.loc[still_failed, "timestamp"], format=fmt, errors="coerce")
                df.loc[still_failed, "timestamp"] = fixed
            except Exception:
                pass

    n_bad = df["timestamp"].isna().sum()
    if n_bad > 0:
        warnings.append(
            f"Could not parse timestamp for {n_bad} row(s); those rows have been dropped."
        )
        df = df[df["timestamp"].notna()]

    return df, warnings
