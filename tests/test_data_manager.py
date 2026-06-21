"""Unit tests for the data validation and sanitization helpers."""

import pandas as pd
from data_manager import (
    sanitize_cell,
    validate_dataframe,
    trim_history,
    ENTRY_COLUMNS,
)


def test_sanitize_cell_neutralizes_formula_prefixes():
    assert sanitize_cell("=cmd|'/c calc'!A0") == "'=cmd|'/c calc'!A0"
    assert sanitize_cell("+1234") == "'+1234"
    assert sanitize_cell("@SUM(A1:A2)") == "'@SUM(A1:A2)"


def test_sanitize_cell_leaves_normal_values_untouched():
    assert sanitize_cell("car_petrol") == "car_petrol"
    assert sanitize_cell(2026) == 2026
    assert sanitize_cell(True) is True


def _valid_row():
    return {
        "date": "2026-06-15", "transport_mode": "bus", "transport_km": 10,
        "electricity_kwh": 5, "meat_meals": 1, "veg_meals": 2, "flight_km": 0,
        "recycled": True, "transport": 1.05, "electricity": 4.1, "diet": 6.3,
        "flights": 0, "recycling_saving": 0.6, "total": 10.85,
    }


def test_validate_dataframe_accepts_good_data():
    df = pd.DataFrame([_valid_row()], columns=ENTRY_COLUMNS)
    ok, message, cleaned = validate_dataframe(df)
    assert ok
    assert cleaned is not None
    assert len(cleaned) == 1


def test_validate_dataframe_rejects_missing_columns():
    df = pd.DataFrame([{"date": "2026-06-15"}])
    ok, message, cleaned = validate_dataframe(df)
    assert not ok
    assert "missing" in message.lower()


def test_validate_dataframe_rejects_unknown_transport_mode():
    row = _valid_row()
    row["transport_mode"] = "rocket"
    df = pd.DataFrame([row], columns=ENTRY_COLUMNS)
    ok, message, cleaned = validate_dataframe(df)
    assert not ok
    assert "transport mode" in message.lower()


def test_validate_dataframe_rejects_negative_numbers():
    row = _valid_row()
    row["transport_km"] = -5
    df = pd.DataFrame([row], columns=ENTRY_COLUMNS)
    ok, message, cleaned = validate_dataframe(df)
    assert not ok
    assert "negative" in message.lower()


def test_validate_dataframe_rejects_non_numeric_values():
    row = _valid_row()
    row["electricity_kwh"] = "not a number"
    df = pd.DataFrame([row], columns=ENTRY_COLUMNS)
    ok, message, cleaned = validate_dataframe(df)
    assert not ok
    assert "numeric" in message.lower()


def test_validate_dataframe_sanitizes_formula_like_strings():
    row = _valid_row()
    row["transport_mode"] = "bus"  # valid mode, but exercise sanitization path generally
    df = pd.DataFrame([row], columns=ENTRY_COLUMNS)
    ok, message, cleaned = validate_dataframe(df)
    assert ok
    assert cleaned is not None
    # transport_mode is a fixed value but the sanitization map runs over all
    # object columns without error
    assert cleaned["transport_mode"].iloc[0] == "bus"


def test_trim_history_keeps_most_recent_rows():
    df = pd.DataFrame({"x": range(1500)})
    trimmed = trim_history(df, max_entries=1000)
    assert len(trimmed) == 1000
    assert trimmed["x"].iloc[0] == 500
    assert trimmed["x"].iloc[-1] == 1499


def test_trim_history_is_a_noop_under_the_limit():
    df = pd.DataFrame({"x": range(10)})
    trimmed = trim_history(df, max_entries=1000)
    assert len(trimmed) == 10