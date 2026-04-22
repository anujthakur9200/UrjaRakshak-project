"""
JWT authentication middleware / dependency.

Usage in a route:
    from app.middleware.auth import require_auth, TokenPayload

    @router.get("/protected")
    async def protected(payload: TokenPayload = Depends(require_auth)):
        return {"user_id": payload.sub}
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "change-me-in-production"
SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", _DEFAULT_SECRET)
ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

if os.getenv("ENVIRONMENT", "development") == "production" and SECRET_KEY == _DEFAULT_SECRET:
    raise RuntimeError(
        "JWT_SECRET_KEY must be set to a strong secret in production. "
        "Refusing to start with the default insecure key."
    )

_bearer = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str                        # subject (user id / email)
    exp: Optional[int] = None       # expiry (UNIX timestamp)
    role: str = "viewer"            # viewer | analyst | admin
    tenant_id: Optional[str] = None


def _decode_token(token: str) -> TokenPayload:
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    exp = claims.get("exp")
    if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPayload(
        sub=claims.get("sub", ""),
        exp=exp,
        role=claims.get("role", "viewer"),
        tenant_id=claims.get("tenant_id"),
    )


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> TokenPayload:
    """FastAPI dependency — raises 401 if no valid Bearer token is present."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(credentials.credentials)


async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[TokenPayload]:
    """Like require_auth but returns None instead of raising for anonymous access."""
    if credentials is None:
        return None
    try:
        return _decode_token(credentials.credentials)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Return a dependency that enforces one of the allowed roles."""

    async def _dep(payload: TokenPayload = Depends(require_auth)) -> TokenPayload:
        if payload.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{payload.role}' is not permitted. Required: {roles}",
            )
        return payload

    return _dep
