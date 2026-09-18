"""
api/auth/routes.py
=================
Authentication and user-administration endpoints.

Mount in api/routes.py:
    from api.auth.routes import router as auth_router
    app.include_router(auth_router)

    @app.on_event("startup")
    def _startup():
        from api.auth.models import ensure_user_indexes, seed_admin
        ensure_user_indexes()
        seed_admin(os.getenv("ADMIN_EMAIL"), os.getenv("ADMIN_PASSWORD"))
"""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from api.auth.security import (
    verify_password, create_access_token, create_refresh_token, safe_decode,
)
from api.auth.models import (
    UserCreate, UserUpdate, UserPublic, TokenPair,
    users, get_user_by_email, create_user, _to_public, record_audit,
)
from api.auth.roles import Role, Permission, permissions_for
from api.auth.deps import get_current_user, require_permission, current_role

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Login (OAuth2 password flow) ───────────────────────────────────────────────
@router.post("/login", response_model=TokenPair)
def login(form: OAuth2PasswordRequestForm = Depends()):
    # OAuth2PasswordRequestForm uses `username`; we treat it as the email.
    user = get_user_by_email(form.username)
    if not user or not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.get("is_active", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is deactivated")

    record_audit(user["email"], "login")
    return TokenPair(
        access_token=create_access_token(user["email"], user["role"]),
        refresh_token=create_refresh_token(user["email"], user["role"]),
    )


# ── Refresh ────────────────────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenPair)
def refresh(refresh_token: str):
    payload = safe_decode(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = get_user_by_email(payload["sub"])
    if not user or not user.get("is_active", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User inactive or not found")
    return TokenPair(
        access_token=create_access_token(user["email"], user["role"]),
        refresh_token=create_refresh_token(user["email"], user["role"]),
    )


# ── Who am I (with resolved permissions for the frontend to gate UI) ───────────
@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    role = current_role(user)
    pub = _to_public(user)
    pub["permissions"] = sorted(p.value for p in permissions_for(role))
    return pub


# ── User administration (admin only) ───────────────────────────────────────────
@router.get("/users", response_model=list[UserPublic])
def list_users(admin: dict = Depends(require_permission(Permission.USER_MANAGE))):
    return [_to_public(u) for u in users.find()]


@router.post("/users", response_model=UserPublic, status_code=201)
def add_user(data: UserCreate,
             admin: dict = Depends(require_permission(Permission.USER_MANAGE))):
    if get_user_by_email(data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    doc = create_user(data)
    record_audit(admin["email"], "user_create", target=data.email,
                 meta={"role": data.role.value})
    return _to_public(doc)


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user(user_id: str, data: UserUpdate,
                admin: dict = Depends(require_permission(Permission.USER_MANAGE))):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid user id")

    changes = {k: (v.value if isinstance(v, Role) else v)
               for k, v in data.model_dump(exclude_none=True).items()}
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No changes provided")

    result = users.find_one_and_update(
        {"_id": oid}, {"$set": changes}, return_document=True,
    )
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    record_audit(admin["email"], "user_update", target=result["email"], meta=changes)
    return _to_public(result)
