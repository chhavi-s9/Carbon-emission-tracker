"""
SQLite persistence layer for Carbon Footprint Coach.

Two tables:
  - users:  id, username, email, password_hash
  - logs:   id, user_id, date, transport_mode, transport_km, electricity_kwh,
            meat_meals, veg_meals, flight_km, recycled, transport, electricity,
            diet, flights, recycling_saving, total

Only logged-in users' entries are ever written here. Guests use
st.session_state only (see data_manager.py) and nothing in this module
is touched for them, so guest data can never be mixed with stored user
data and is never persisted.
"""

import sqlite3
from contextlib import contextmanager

DB_PATH = "carbon_coach.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                transport_mode TEXT NOT NULL,
                transport_km REAL NOT NULL,
                electricity_kwh REAL NOT NULL,
                meat_meals INTEGER NOT NULL,
                veg_meals INTEGER NOT NULL,
                flight_km REAL NOT NULL,
                recycled INTEGER NOT NULL,
                transport REAL NOT NULL,
                electricity REAL NOT NULL,
                diet REAL NOT NULL,
                flights REAL NOT NULL,
                recycling_saving REAL NOT NULL,
                total REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username: str, email: str, password_hash: str) -> tuple[bool, str]:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash),
            )
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "That username or email is already registered."


def get_user_by_username(username: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def add_log(user_id: int, row: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO logs (
                user_id, date, transport_mode, transport_km, electricity_kwh,
                meat_meals, veg_meals, flight_km, recycled,
                transport, electricity, diet, flights, recycling_saving, total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, row["date"], row["transport_mode"], row["transport_km"],
                row["electricity_kwh"], row["meat_meals"], row["veg_meals"],
                row["flight_km"], int(row["recycled"]),
                row["transport"], row["electricity"], row["diet"],
                row["flights"], row["recycling_saving"], row["total"],
            ),
        )


def get_logs_for_user(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM logs WHERE user_id = ? ORDER BY date ASC, id ASC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
