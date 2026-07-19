from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import os
import secrets
import time
from enum import StrEnum
from typing import Any, Callable
from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.exceptions import SecurityConfigError

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Security Settings — centralised, validated at import time
# ---------------------------------------------------------------------------

_SECRET_DENYLIST = {
    "dev-lexsocial-secret-change-me",
    "secret",
    "changeme",
    "password",
    "test",
    "development",
}

_SECRET_WEAK_PATTERNS = [
    "change-me", "changeme", "example", "default", "your-secret", "replace-me",
]

_PRODUCTION_ENVS = {"production", "staging"}
_DEV_ENVS = {"development", "local", "test"}


class SecuritySettings:
    """Immutable security configuration resolved once at import time."""

    __slots__ = ("auth_token_secret", "enable_dev_tokens", "app_env", "token_ttl_s")

    def __init__(self) -> None:
        self.app_env: str = os.getenv("APP_ENV", "development").lower().strip()
        self.enable_dev_tokens: bool = os.getenv("ENABLE_DEV_TOKENS", "false").lower() in {"1", "true", "yes"}
        self.token_ttl_s: int = int(os.getenv("AUTH_TOKEN_TTL_S") or "43200")

        raw_secret = os.getenv("AUTH_TOKEN_SECRET")

        if self.app_env in _PRODUCTION_ENVS:
            # Production: validate, but NEVER abort process boot (Railway health/proxy).
            problems: list[str] = []
            if not raw_secret:
                problems.append("AUTH_TOKEN_SECRET missing")
            elif len(raw_secret) < 32:
                problems.append(f"AUTH_TOKEN_SECRET too short ({len(raw_secret)} chars)")
            elif raw_secret.lower() in _SECRET_DENYLIST:
                problems.append("AUTH_TOKEN_SECRET is a denylisted weak value")
            else:
                for pattern in _SECRET_WEAK_PATTERNS:
                    if pattern in raw_secret.lower():
                        problems.append(f"AUTH_TOKEN_SECRET contains weak pattern '{pattern}'")
                        break
            if self.enable_dev_tokens:
                problems.append("ENABLE_DEV_TOKENS must be false in production")
                self.enable_dev_tokens = False

            if problems:
                logger.critical(
                    "Insecure production auth config — using ephemeral secret so the process stays up. %s",
                    "; ".join(problems),
                )
                self.auth_token_secret = secrets.token_urlsafe(48)
            else:
                self.auth_token_secret = raw_secret  # type: ignore[assignment]
        else:
            # Development / Test / Local
            if raw_secret:
                self.auth_token_secret = raw_secret
            else:
                self.auth_token_secret = secrets.token_urlsafe(48)
                logger.warning(
                    "AUTH_TOKEN_SECRET not set — generated ephemeral secret for this process. "
                    "Tokens will NOT survive restarts. Set AUTH_TOKEN_SECRET in .env for persistence.",
                    extra={"app_env": self.app_env},
                )

    def __repr__(self) -> str:
        # Never leak the secret in logs/repr
        return (
            f"SecuritySettings(app_env={self.app_env!r}, "
            f"enable_dev_tokens={self.enable_dev_tokens}, "
            f"token_ttl_s={self.token_ttl_s}, "
            f"auth_token_secret=<REDACTED {len(self.auth_token_secret)} chars>)"
        )


# Singleton — never abort process boot (Railway needs a listening port).
_SETTINGS: SecuritySettings | None = None


def get_security_settings() -> SecuritySettings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = SecuritySettings()
    return _SETTINGS


get_security_settings()


def security_boot_error() -> str | None:
    """Kept for /health compatibility; production soft-fallback no longer sets this."""
    return None


_TOKEN_PREFIX = "lx1"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(user_id: str, email: str | None, role: str, ttl_s: int | None = None) -> str:
    """Mint a signed session token encoding the user's id/email/role and an expiry."""
    settings = get_security_settings()
    payload = {"uid": user_id, "eml": email, "rol": role, "exp": int(time.time()) + (ttl_s or settings.token_ttl_s)}
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(settings.auth_token_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{_TOKEN_PREFIX}.{payload_b64}.{sig}"


def _verify_signed_token(token: str) -> "UserToken | None":
    """Validate an ``lx1.`` token: correct signature + not expired. Returns None otherwise."""
    try:
        prefix, payload_b64, sig = token.split(".")
        if prefix != _TOKEN_PREFIX:
            return None
        settings = get_security_settings()
        expected = hmac.new(settings.auth_token_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        role = str(payload.get("rol") or Role.CITIZEN.value)
        return UserToken(user_id=str(payload.get("uid") or "user"), email=payload.get("eml"), roles=[role])
    except Exception:  # noqa: BLE001 — Boundary: any malformed token is simply rejected
        return None


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


# ---------------------------------------------------------------------------
# Dev shortcut tokens — gated behind ENABLE_DEV_TOKENS
# ---------------------------------------------------------------------------

_DEV_TOKEN_MAP: dict[str, UserToken] = {
    "test-admin-phap-che": UserToken(user_id="user-phap-che-1", email="phapche@admin.gov.vn", roles=[Role.ADMIN_PHAP_CHE.value]),
    "test-admin-truyen-thong": UserToken(user_id="user-truyen-thong-1", email="truyenthong@admin.gov.vn", roles=[Role.ADMIN_TRUYEN_THONG.value]),
    "test-admin-ops": UserToken(user_id="user-ops-1", email="ops@admin.gov.vn", roles=[Role.ADMIN_OPS.value]),
    "test-admin-multi": UserToken(
        user_id="user-multi-1",
        email="multi@admin.gov.vn",
        roles=[Role.ADMIN_PHAP_CHE.value, Role.ADMIN_TRUYEN_THONG.value, Role.ADMIN_OPS.value],
    ),
    "test-citizen": UserToken(user_id="user-citizen-1", email="citizen@gmail.com", roles=[Role.CITIZEN.value]),
}


def _try_dev_token(token_str: str) -> UserToken | None:
    """Return a dev-shortcut UserToken if feature is enabled and the token matches exactly."""
    settings = get_security_settings()
    if not settings.enable_dev_tokens:
        return None
    user = _DEV_TOKEN_MAP.get(token_str)
    if user is not None:
        logger.warning(
            "Dev shortcut token authenticated",
            extra={"authentication_method": "dev_token", "role": user.roles[0], "app_env": settings.app_env},
        )
    return user


def decode_or_mock_token(token_str: str | None) -> UserToken:
    """Decode JWT or support local/test bearer tokens for deterministic evaluation."""
    if not token_str:
        return UserToken(user_id="anon", roles=[Role.ANONYMOUS.value])

    t = token_str.strip()
    if t.startswith("Bearer "):
        t = t[7:].strip()

    # Dev shortcut tokens — only when explicitly enabled outside production.
    dev_user = _try_dev_token(t)
    if dev_user is not None:
        return dev_user

    # Real signed session token (issued by /auth/login after verifying the Postgres users table).
    if t.startswith(_TOKEN_PREFIX + "."):
        verified = _verify_signed_token(t)
        # Fail-closed: an lx1 token that fails signature/expiry is anonymous, never citizen-by-default.
        return verified if verified is not None else UserToken(user_id="anon", roles=[Role.ANONYMOUS.value])

    # Unknown bearer strings are anonymous (never invent citizen privilege from garbage tokens).
    return UserToken(user_id="anon", roles=[Role.ANONYMOUS.value])


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
