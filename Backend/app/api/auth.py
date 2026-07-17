from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_db_pool
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.core.security import issue_token, get_current_user, UserToken, ADMIN_ROLES

router = APIRouter(tags=["Auth"])

_ADMIN_ROLE_VALUES = {r.value for r in ADMIN_ROLES}


class LoginRequest(BaseModel):
    email: str = Field(..., description="Email đăng nhập (khớp cột users.email)")
    password: str = Field(..., min_length=1, description="Mật khẩu (đối chiếu bcrypt qua pgcrypto)")


@router.post("/auth/login", summary="Đăng nhập bằng tài khoản trong bảng users (Postgres)")
async def login(request: LoginRequest, pool: Any = Depends(get_db_pool)) -> dict[str, Any]:
    """Verify credentials against the Postgres ``users`` table (bcrypt via pgcrypto ``crypt()``).

    On success returns a signed session token + user info. Never reveals whether the email exists.
    """
    if pool is None or not hasattr(pool, "acquire"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cơ sở dữ liệu chưa sẵn sàng, không thể đăng nhập.",
        )

    email = request.email.strip().lower()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, email, full_name, role::text AS role
                FROM users
                WHERE lower(email) = $1
                  AND is_active = TRUE
                  AND hashed_password = crypt($2, hashed_password)
                """,
                email,
                request.password,
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lỗi truy vấn xác thực: {exc}",
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng.")

    role = str(row["role"])
    token = issue_token(user_id=str(row["id"]), email=str(row["email"]), role=role)
    data = {
        "token": token,
        "user": {
            "id": str(row["id"]),
            "email": str(row["email"]),
            "full_name": row["full_name"],
            "role": role,
            "roles": [role],
            "is_admin": role in _ADMIN_ROLE_VALUES,
        },
    }
    return success_response(data=data, request_id=get_request_id())


@router.get("/auth/me", summary="Thông tin người dùng hiện tại (giải mã từ token)")
async def me(user: UserToken = Depends(get_current_user)) -> dict[str, Any]:
    data = {
        "user_id": user.user_id,
        "email": user.email,
        "roles": user.roles,
        "is_admin": user.is_admin(),
    }
    return success_response(data=data, request_id=get_request_id())
