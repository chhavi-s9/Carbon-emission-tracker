"""
Authentication helpers: password hashing (PBKDF2-SHA256 via hashlib,
no extra dependency), signup/login validation, and Streamlit session
helpers for tracking the current user.

Design choice: passwords are hashed with a per-user random salt using
hashlib.pbkdf2_hmac. This avoids adding a new dependency (e.g. bcrypt)
under time pressure while still never storing plaintext passwords.
"""

import hashlib
import hmac
import os
import re

import streamlit as st

import database as db

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """Return 'salt$hash' (both hex) for storage."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(candidate, expected)


def _valid_email(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def signup(username: str, email: str, password: str) -> tuple[bool, str]:
    username = username.strip()
    email = email.strip().lower()

    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not _valid_email(email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    password_hash = hash_password(password)
    ok, message = db.create_user(username, email, password_hash)
    if not ok:
        return False, message

    user = db.get_user_by_username(username)
    _start_session(user)
    return True, "Account created! Redirecting to your dashboard..."


def login(username: str, password: str) -> tuple[bool, str]:
    user = db.get_user_by_username(username.strip())
    if not user or not verify_password(password, user["password_hash"]):
        return False, "Incorrect username or password."
    _start_session(user)
    return True, "Welcome back!"


def logout() -> None:
    for key in ("user_id", "username", "logged_in"):
        st.session_state.pop(key, None)


def _start_session(user: dict) -> None:
    st.session_state["user_id"] = user["id"]
    st.session_state["username"] = user["username"]
    st.session_state["logged_in"] = True


def is_logged_in() -> bool:
    return bool(st.session_state.get("logged_in"))


def current_user_id():
    return st.session_state.get("user_id")


def current_username() -> str:
    return st.session_state.get("username", "")
