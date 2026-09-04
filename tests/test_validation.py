"""
Tests for CSV validation module.
"""
import pytest
from src.core.validation import validate_and_parse

VALID_CSV = """transaction_id,timestamp,description,payee,amount,channel
TX001,2025-10-01 09:15,Groceries,Fresh Mart,1200,UPI
TX002,2025-10-02 10:00,Salary,ABC Corp,65000,BANK_TRANSFER
TX003,2025-10-03 12:00,Fuel,HP Petrol,2800,DEBIT_CARD
"""

def test_valid_csv_parses_correctly():
    result = validate_and_parse(VALID_CSV)
    assert result.is_valid
    assert len(result.transactions) == 3
    assert result.transactions[0].transaction_id == "TX001"
    assert result.transactions[1].amount == 65000.0

def test_empty_csv_returns_error():
    result = validate_and_parse("")
    assert not result.is_valid
    assert any("empty" in e.lower() for e in result.errors)

def test_missing_required_column():
    csv = "description,payee,amount\nGroceries,Fresh Mart,1200"
    result = validate_and_parse(csv)
    assert not result.is_valid
    assert any("transaction_id" in e or "timestamp" in e for e in result.errors)

def test_malformed_timestamp_dropped():
    csv = """transaction_id,timestamp,amount
TX001,not-a-date,1200
TX002,2025-10-01 09:00,2000"""
    result = validate_and_parse(csv)
    # TX001 should be dropped; TX002 kept
    assert result.is_valid
    assert any("TX001" not in t.transaction_id for t in result.transactions)
    assert result.row_count_valid == 1

def test_negative_amount_dropped():
    csv = """transaction_id,timestamp,amount
TX001,2025-10-01 09:00,-500
TX002,2025-10-02 09:00,1000"""
    result = validate_and_parse(csv)
    assert result.is_valid
    assert len(result.transactions) == 1
    assert result.transactions[0].transaction_id == "TX002"

def test_duplicate_rows_removed():
    csv = """transaction_id,timestamp,description,payee,amount,channel
TX001,2025-10-01 09:15,Groceries,Fresh Mart,1200,UPI
TX001,2025-10-01 09:15,Groceries,Fresh Mart,1200,UPI"""
    result = validate_and_parse(csv)
    assert result.is_valid
    assert len(result.transactions) == 1

def test_column_aliases():
    csv = """txn_id,date,narration,beneficiary,amt,mode
TX001,2025-10-01,Groceries,Fresh Mart,1200,UPI"""
    result = validate_and_parse(csv)
    assert result.is_valid
    assert result.transactions[0].transaction_id == "TX001"
    assert result.transactions[0].amount == 1200.0

def test_single_transaction_low_confidence_warning():
    csv = """transaction_id,timestamp,amount
TX001,2025-10-01 09:00,1200"""
    result = validate_and_parse(csv)
    assert result.is_valid
    assert len(result.transactions) == 1
    assert any("limited" in w.lower() or "only" in w.lower() for w in result.warnings)
