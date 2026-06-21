"""
Session-based data layer with CSV export/import.

Data lives in Streamlit's session state for the duration of a user's
session. This is a deliberate security/privacy choice: a single shared
CSV file on disk would mix data between every visitor on a public
deployment. Users can download their history and re-upload it to continue
in a future session.

A soft cap (MAX_HISTORY_ENTRIES) bounds how much each session can grow,
protecting server memory on a shared deployment without affecting normal
day-to-day use.

The validation/sanitization/trim functions below are pure (no Streamlit
dependency) so they can be unit tested directly.
"""

import pandas as pd
import streamlit as st

import database as db

ENTRY_COLUMNS = [
    "date", "transport_mode", "transport_km", "electricity_kwh",
    "meat_meals", "veg_meals", "flight_km", "recycled",
    "transport", "electricity", "diet", "flights", "recycling_saving", "total",
]

NUMERIC_COLUMNS = [c for c in ENTRY_COLUMNS if c not in ("date", "transport_mode", "recycled")]

ALLOWED_TRANSPORT_MODES = {
    "car_petrol", "car_diesel", "car_cng", "two_wheeler",
    "bus", "metro_train", "ev_car", "bicycle_walk",
}

# Leading characters that spreadsheet programs interpret as formulas.
_CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@")

# Soft cap on rows kept per session, to bound memory on a shared deployment.
MAX_HISTORY_ENTRIES = 1000


def sanitize_cell(value):
    """
    Defuse CSV/spreadsheet formula injection.

    If a string value starts with a character that Excel/Sheets treats as
    the start of a formula, prefix it with a single quote so it is rendered
    as plain text instead of being executed.
    """
    if isinstance(value, str) and value.startswith(_CSV_DANGEROUS_PREFIXES):
        return "'" + value
    return value


def trim_history(df: pd.DataFrame, max_entries: int = MAX_HISTORY_ENTRIES) -> pd.DataFrame:
    """
    Keep only the most recent `max_entries` rows.

    Pure and side-effect free so it can be tested directly. Used both when
    appending a new daily entry and when importing a CSV, so a single
    session can never grow unbounded.
    """
    if len(df) <= max_entries:
        return df
    return df.tail(max_entries).reset_index(drop=True)


def validate_dataframe(df: pd.DataFrame) -> tuple[bool, str, pd.DataFrame | None]:
    """
    Validate an uploaded history dataframe.

    Returns (is_valid, message, cleaned_dataframe). cleaned_dataframe is
    None if validation failed.
    """
    missing = set(ENTRY_COLUMNS) - set(df.columns)
    if missing:
        return False, f"File is missing expected columns: {', '.join(sorted(missing))}", None

    df = df[ENTRY_COLUMNS].copy()

    modes = set(df["transport_mode"].dropna().unique())
    if not modes.issubset(ALLOWED_TRANSPORT_MODES):
        return False, "File contains an unrecognized transport mode.", None

    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[NUMERIC_COLUMNS].isna().any().any():
        return False, "File contains non-numeric values in a numeric column.", None

    if (df[NUMERIC_COLUMNS] < 0).any().any():
        return False, "File contains negative values, which are not valid.", None

    df["recycled"] = df["recycled"].astype(bool)

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].map(sanitize_cell)

    return True, f"Loaded {len(df)} entries.", df.reset_index(drop=True)


def _init_state() -> None:
    if "history" not in st.session_state:
        st.session_state.history = pd.DataFrame(columns=ENTRY_COLUMNS)
    if "actions" not in st.session_state:
        st.session_state.actions = {}


def get_history() -> pd.DataFrame:
    """Return the current session's logged entries."""
    _init_state()
    return st.session_state.history


def add_entry(entry_row: dict) -> None:
    """Append a single computed daily entry to the session's history."""
    _init_state()
    sanitized = {k: sanitize_cell(v) for k, v in entry_row.items()}
    new_row = pd.DataFrame([sanitized], columns=ENTRY_COLUMNS)
    combined = pd.concat([st.session_state.history, new_row], ignore_index=True)
    st.session_state.history = trim_history(combined)


def export_history_csv() -> bytes:
    """Export the session's history as CSV bytes for download."""
    _init_state()
    return st.session_state.history.to_csv(index=False).encode("utf-8")


def import_history_csv(uploaded_file) -> tuple[bool, str]:
    """Validate and load a previously exported CSV into the session."""
    try:
        df = pd.read_csv(uploaded_file)
    except Exception:
        return False, "Could not read that file as CSV."

    is_valid, message, cleaned = validate_dataframe(df)
    if not is_valid or cleaned is None:
        return False, message

    trimmed = trim_history(cleaned)
    if len(trimmed) < len(cleaned):
        message += f" (kept the most recent {MAX_HISTORY_ENTRIES} entries)"

    _init_state()
    st.session_state.history = trimmed
    return True, message

def get_actions() -> dict:
    _init_state()
    return st.session_state.actions


def set_actions(actions: dict) -> None:
    _init_state()
    st.session_state.actions = actions


# ---------------------------------------------------------------------------
# Login-aware helpers
# ---------------------------------------------------------------------------
# Guests keep using get_history()/add_entry() above (pure session_state,
# never written to disk). Logged-in users get their entries persisted to
# SQLite under their own user_id, and only ever read back their own rows
# (filtered by user_id in database.py), so user data is never mixed.

def get_history_for_user(user_id) -> pd.DataFrame:
    """Return a logged-in user's full history from SQLite as a DataFrame
    shaped like ENTRY_COLUMNS, identical to the guest session DataFrame."""
    rows = db.get_logs_for_user(user_id)
    if not rows:
        return pd.DataFrame(columns=ENTRY_COLUMNS)
    df = pd.DataFrame(rows)
    df["recycled"] = df["recycled"].astype(bool)
    return df[ENTRY_COLUMNS]


def add_entry_for_user(user_id, entry_row: dict) -> None:
    """Persist a single computed daily entry for a logged-in user."""
    sanitized = {k: sanitize_cell(v) for k, v in entry_row.items()}
    db.add_log(user_id, sanitized)


def get_current_history(user_id=None) -> pd.DataFrame:
    """Single entry point used by app.py: DB-backed history if logged in,
    otherwise the guest's session-only history."""
    if user_id is not None:
        return get_history_for_user(user_id)
    return get_history()


def add_current_entry(entry_row: dict, user_id=None) -> None:
    """Single entry point used by app.py: persist to SQLite if logged in,
    otherwise keep it in the guest's session only."""
    if user_id is not None:
        add_entry_for_user(user_id, entry_row)
    else:
        add_entry(entry_row)