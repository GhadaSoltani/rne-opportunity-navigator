"""
api/auth/models.py
=================
User schema (Pydantic) and a MongoDB-backed user store + audit log.

Reuses the existing Mongo client from db/documents.py so we don't open a second
connection. Users live in the `users` collection; mutating actions are recorded
in the `audit_log` collection.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from db.documents import db  # existing MongoClient["rne_database"]
from api.auth.roles import Role
from api.auth.security import hash_password

users = db["users"]
audit_log = db["audit_log"]


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas (API contracts)
# ─────────────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: Role
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = None


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    must_reset_password: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ─────────────────────────────────────────────────────────────────────────────
# Store helpers
# ─────────────────────────────────────────────────────────────────────────────

def ensure_user_indexes():
    users.create_index("email", unique=True)


def _to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "full_name": doc.get("full_name", ""),
        "role": doc["role"],
        "is_active": doc.get("is_active", True),
        "must_reset_password": doc.get("must_reset_password", False),
    }


def get_user_by_email(email: str) -> Optional[dict]:
    return users.find_one({"email": email.lower()})


def create_user(data: UserCreate, must_reset: bool = True) -> dict:
    doc = {
        "email": data.email.lower(),
        "full_name": data.full_name,
        "role": data.role.value,
        "hashed_password": hash_password(data.password),
        "is_active": True,
        "must_reset_password": must_reset,
        "created_at": datetime.now(timezone.utc),
    }
    result = users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def seed_admin(email: str, password: str, full_name: str = "Administrator") -> Optional[dict]:
    """Create the first admin if no users exist. Safe to call on startup."""
    if users.count_documents({}) > 0:
        return None
    return create_user(
        UserCreate(email=email, full_name=full_name, role=Role.ADMIN, password=password),
        must_reset=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────────────────

def record_audit(actor_email: str, action: str, target: str = "", meta: dict | None = None):
    """Append an immutable-ish audit record for any mutating action."""
    audit_log.insert_one({
        "actor": actor_email,
        "action": action,
        "target": target,
        "meta": meta or {},
        "at": datetime.now(timezone.utc),
    })
