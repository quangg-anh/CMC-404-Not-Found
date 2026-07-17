from __future__ import annotations

import hmac
import hashlib
from enum import StrEnum
from typing import Any, Callable
from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security_bearer = HTTPBearer(auto_error=False)


class Role(StrEnum):
    ADMIN_PHAP_CHE = "admin_phap_che"
    ADMIN_TRUYEN_THONG = "admin_truyen_thong"
    ADMIN_OPS = "admin_ops"
    CITIZEN = "citizen"
    ANONYMOUS = "anonymous"


ADMIN_ROLES = {Role.ADMIN_PHAP_CHE, Role.ADMIN_TRUYEN_THONG, Role.ADMIN_OPS}
ALL_ROLES = set(Role)


class UserToken(BaseModel):
    user_id: str = Field(default="anonymous-user", description="User ID or sub")
    email: str | None = None
    roles: list[str] = Field(default_factory=lambda: [Role.ANONYMOUS.value])
    tenant_id: str | None = None

    def has_any_role(self, required_roles: set[str] | list[str]) -> bool:
        req = set(required_roles)
        return any(role in req for role in self.roles)

    def is_admin(self) -> bool:
        return any(role in ADMIN_ROLES for role in self.roles)

    def is_citizen_only(self) -> bool:
        return not self.is_admin() and any(role in {Role.CITIZEN, Role.ANONYMOUS} for role in self.roles)


def decode_or_mock_token(token_str: str | None) -> UserToken:
    """Decode JWT or support local/test bearer tokens for deterministic evaluation."""
    if not token_str:
        return UserToken(user_id="anon", roles=[Role.ANONYMOUS.value])

    t = token_str.strip()
    if t.startswith("Bearer "):
        t = t[7:].strip()

    # Deterministic test/dev shortcuts. EXACT match only — substring matching ("admin_ops" in t)
    # is a privilege-escalation hole (any string containing the marker would grant admin), so a
    # role must be granted only for the precise dev token, never for an arbitrary token that
    # merely happens to contain the marker.
    if t == "test-admin-phap-che":
        return UserToken(user_id="user-phap-che-1", email="phapche@admin.gov.vn", roles=[Role.ADMIN_PHAP_CHE.value])
    if t == "test-admin-truyen-thong":
        return UserToken(user_id="user-truyen-thong-1", email="truyenthong@admin.gov.vn", roles=[Role.ADMIN_TRUYEN_THONG.value])
    if t == "test-admin-ops":
        return UserToken(user_id="user-ops-1", email="ops@admin.gov.vn", roles=[Role.ADMIN_OPS.value])
    if t == "test-admin-multi":
        return UserToken(
            user_id="user-multi-1",
            email="multi@admin.gov.vn",
            roles=[Role.ADMIN_PHAP_CHE.value, Role.ADMIN_TRUYEN_THONG.value, Role.ADMIN_OPS.value],
        )
    if t == "test-citizen":
        return UserToken(user_id="user-citizen-1", email="citizen@gmail.com", roles=[Role.CITIZEN.value])

    # Any other bearer string is treated as an unprivileged citizen (never admin). A real JWT
    # verifier should replace this branch in production.
    return UserToken(user_id=f"user-{t[:8]}", roles=[Role.CITIZEN.value])


async def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Security(security_bearer),
) -> UserToken:
    """Extract and decode user from Authorization header."""
    if not auth or not auth.credentials:
        return UserToken(user_id="anon", roles=[Role.ANONYMOUS.value])
    return decode_or_mock_token(auth.credentials)


def require_roles(*allowed_roles: str | Role) -> Callable[[UserToken], UserToken]:
    """Dependency factory ensuring user has at least one of the required roles."""
    allowed_set = {r.value if isinstance(r, Role) else r for r in allowed_roles}

    def role_checker(user: UserToken = Depends(get_current_user)) -> UserToken:
        if user.is_citizen_only() and any(r in ADMIN_ROLES for r in allowed_set):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Portal Isolation: Citizen access Forbidden on admin endpoints.",
            )
        if not user.has_any_role(allowed_set):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User lacks required roles: {sorted(list(allowed_set))}",
            )
        return user

    return role_checker


def require_admin() -> Callable[[UserToken], UserToken]:
    """Dependency ensuring user has any admin role."""
    return require_roles(*ADMIN_ROLES)


def verify_hmac_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify HMAC SHA256 signature for webhooks/callbacks."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
