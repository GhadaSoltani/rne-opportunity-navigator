"""
api/auth/security.py
====================
Password hashing (Argon2) and JWT creation/verification.

Secrets come from the environment, never from code:
    JWT_SECRET                 signing key (REQUIRED in production)
    JWT_ALGORITHM              default HS256
    ACCESS_TOKEN_MINUTES       default 30
    REFRESH_TOKEN_DAYS         default 7

Dependencies (add to requirements.txt):
    passlib[argon2]
    python-jose[cryptography]
"""

import os
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

# Argon2 is the current best-practice password hash. bcrypt is a fine fallback.
_pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

JWT_SECRET       = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
JWT_ALGORITHM    = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_MINUTES   = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
REFRESH_DAYS     = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))


# ── passwords ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ── tokens ───────────────────────────────────────────────────────────────────

def _create_token(subject: str, role: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub":  subject,          # user id / email
        "role": role,
        "type": token_type,       # "access" | "refresh"
        "iat":  now,
        "exp":  now + expires,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(subject: str, role: str) -> str:
    return _create_token(subject, role, "access", timedelta(minutes=ACCESS_MINUTES))


def create_refresh_token(subject: str, role: str) -> str:
    return _create_token(subject, role, "refresh", timedelta(days=REFRESH_DAYS))


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises JWTError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def safe_decode(token: str) -> dict | None:
    try:
        return decode_token(token)
    except JWTError:
        return None
