"""
UrjaRakshak — Authentication & Authorization
=============================================
JWT-based authentication with Role-Based Access Control.

Roles:
  admin   — Full access. Can manage users, view all data, retrain models.
  analyst — Can run analyses, view all results. Cannot manage users.
  viewer  — Read-only access to dashboards and reports.

Security:
  - bcrypt password hashing (cost factor 12)
  - HS256 JWT tokens
  - Token expiry enforced
  - Role hierarchy enforced at route level
  - No plaintext passwords stored

Author: Vipin Baniya
"""

from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any
import logging

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models.db_models import User

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── JWT Bearer scheme ─────────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)

# ── Constants ─────────────────────────────────────────────────────────────
ALGORITHM = "HS256"
ROLE_HIERARCHY = {"admin": 3, "analyst": 2, "viewer": 1}


# ── Pydantic schemas ──────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    user_id: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Password must be between 8 and 72 characters"
    )
    full_name: Optional[str] = None
    role: str = Field(default="viewer", pattern="^(admin|analyst|viewer)$")
    date_of_birth: Optional[date] = None         # YYYY-MM-DD
    security_question: Optional[str] = None
    security_answer: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PasswordResetVerify(BaseModel):
    """Step 1 — verify identity before resetting password."""
    email: EmailStr
    date_of_birth: Optional[date] = None         # YYYY-MM-DD
    security_answer: Optional[str] = None


class PasswordReset(BaseModel):
    """Step 2 — set a new password after identity is verified."""
    email: EmailStr
    date_of_birth: Optional[date] = None
    security_answer: Optional[str] = None
    new_password: str = Field(..., min_length=8, max_length=72)


class UserPublic(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    has_recovery: bool = False                   # True when DOB/security answer is set

    class Config:
        from_attributes = True


class TokenData(BaseModel):
    user_id: str
    email: str
    role: str


# ── Core auth functions ───────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Hash password with bcrypt.

    bcrypt has a hard limit of 72 bytes.
    We truncate safely to avoid runtime errors.
    """
    password = password[:72]
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    plain = plain[:72]
    return pwd_context.verify(plain, hashed)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    to_encode["iat"] = datetime.utcnow()
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        if not user_id or not email or not role:
            raise JWTError("Missing required claims")
        return TokenData(user_id=user_id, email=email, role=role)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Database helpers ──────────────────────────────────────────────────────

async def get_user_by_email(email: str, db: AsyncSession) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(user_id: str, db: AsyncSession) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(email: str, password: str, db: AsyncSession) -> Optional[User]:
    """Authenticate user by email + password"""
    user = await get_user_by_email(email, db)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


async def create_user(user_data: UserCreate, db: AsyncSession) -> User:
    """Create a new user.

    First user ever registered is automatically promoted to admin.
    Subsequent users receive the role supplied in user_data (default 'viewer').
    """
    from sqlalchemy import func as sql_func
    # Check email not already taken
    existing = await get_user_by_email(user_data.email, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Auto-promote to admin if this is the very first user
    count_result = await db.execute(select(sql_func.count()).select_from(User))
    user_count = count_result.scalar() or 0
    effective_role = "admin" if user_count == 0 else user_data.role

    # Prepare optional recovery fields
    dob = user_data.date_of_birth if user_data.date_of_birth else None
    sec_q = user_data.security_question.strip() if user_data.security_question else None
    sec_a_hash: Optional[str] = None
    if user_data.security_answer:
        sec_a_hash = hash_password(user_data.security_answer.strip().lower())

    user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=effective_role,
        date_of_birth=dob,
        security_question=sec_q,
        security_answer_hash=sec_a_hash,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"New user created: {user.email} ({user.role})")
    return user


# ── FastAPI dependencies ──────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    token: Optional[str] = Query(default=None, description="JWT token (for SSE / EventSource which cannot set headers)"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency — extracts and validates JWT, returns User.

    Accepts token from two sources (in priority order):
      1. Authorization: Bearer <token>  (standard — all REST calls)
      2. ?token=<token> query param     (SSE fallback — EventSource cannot set headers)
    """
    raw_token: Optional[str] = None
    if credentials is not None:
        raw_token = credentials.credentials
    elif token is not None:
        raw_token = token

    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(raw_token)
    user = await get_user_by_id(token_data.user_id, db)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Dependency for any authenticated user"""
    return current_user


def require_role(minimum_role: str):
    """
    Role-based access control dependency factory.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        @router.post("/analysis", dependencies=[Depends(require_role("analyst"))])
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(minimum_role, 99)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {minimum_role}, your role: {current_user.role}",
            )
        return current_user
    return role_checker


# Convenient pre-built dependencies
require_admin = require_role("admin")
require_analyst = require_role("analyst")
require_viewer = require_role("viewer")
