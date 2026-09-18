"""
api/auth/deps.py
================
FastAPI dependencies for authentication and role-based access control.

    get_current_user       decode the bearer token → the active user dict
    require_permission(p)  a dependency factory that enforces one Permission
    require_role(*roles)   a dependency factory that enforces membership

Usage in a route:

    @router.get("/prospects")
    def list_prospects(user = Depends(require_permission(Permission.PROSPECT_VIEW_ALL))):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from api.auth.security import safe_decode
from api.auth.models import get_user_by_email
from api.auth.roles import Role, Permission, has_permission

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CRED_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = safe_decode(token)
    if not payload or payload.get("type") != "access":
        raise _CRED_EXC

    email = payload.get("sub")
    if not email:
        raise _CRED_EXC

    user = get_user_by_email(email)
    if not user or not user.get("is_active", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User inactive or not found")

    return user


def current_role(user: dict) -> Role:
    try:
        return Role(user["role"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown role")


def require_permission(permission: Permission):
    """Dependency factory: allow only users whose role holds `permission`."""
    def _guard(user: dict = Depends(get_current_user)) -> dict:
        role = current_role(user)
        if not has_permission(role, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Missing permission: {permission.value}",
            )
        return user
    return _guard


def require_role(*roles: Role):
    """Dependency factory: allow only users in one of `roles`."""
    allowed = set(roles)

    def _guard(user: dict = Depends(get_current_user)) -> dict:
        if current_role(user) not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Role not permitted for this action",
            )
        return user
    return _guard
