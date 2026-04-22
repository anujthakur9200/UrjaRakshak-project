"""
UrjaRakshak — Auth API Endpoints
==================================
POST /api/v1/auth/register              — Create account
POST /api/v1/auth/login                 — Get JWT token
GET  /api/v1/auth/me                    — Get current user
POST /api/v1/auth/forgot-password/verify — Verify identity via DOB / security answer
POST /api/v1/auth/forgot-password/reset  — Reset password after identity verified
GET  /api/v1/auth/users                 — List users (admin only)

Author: Vipin Baniya
"""

from datetime import timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth import (
    UserCreate, UserLogin, UserPublic, TokenResponse,
    PasswordResetVerify, PasswordReset,
    authenticate_user, create_user, create_access_token,
    get_current_active_user, require_admin,
    get_user_by_email, verify_password, hash_password,
)
from app.models.db_models import User
from app.config import settings

router = APIRouter()


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user account.

    The very first registration automatically receives the 'admin' role.
    Subsequent registrations receive the role supplied in the request body
    (default: 'viewer').
    """
    user = await create_user(user_data, db)
    pub = UserPublic.model_validate(user)
    pub.has_recovery = bool(user.date_of_birth or user.security_answer_hash)
    return pub


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Login and receive a JWT access token.

    Token expires in ACCESS_TOKEN_EXPIRE_MINUTES (default: 30 min).
    Include token in subsequent requests as: Authorization: Bearer <token>
    """
    user = await authenticate_user(credentials.email, credentials.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login
    from datetime import datetime
    user.last_login = datetime.utcnow()
    await db.commit()

    access_token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
        user_id=user.id,
    )


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current authenticated user profile"""
    pub = UserPublic.model_validate(current_user)
    pub.has_recovery = bool(current_user.date_of_birth or current_user.security_answer_hash)
    return pub


# ── Forgot password ───────────────────────────────────────────────────────

@router.post("/forgot-password/verify")
async def forgot_password_verify(
    payload: PasswordResetVerify,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1 — verify the user's identity using DOB and/or security answer.
    Returns a short-lived reset token on success (valid 15 min).
    """
    user = await get_user_by_email(payload.email, db)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with that email")

    verified = False

    # Verify via DOB
    if payload.date_of_birth and user.date_of_birth:
        if payload.date_of_birth == user.date_of_birth:
            verified = True

    # Verify via security answer (check even if DOB already passed)
    if payload.security_answer and user.security_answer_hash:
        if verify_password(payload.security_answer.strip().lower(), user.security_answer_hash):
            verified = True

    if not verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identity verification failed. Check your date of birth or security answer.",
        )

    # Issue a one-time reset token (role = 'password_reset' to scope it)
    reset_token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": "password_reset"},
        expires_delta=timedelta(minutes=15),
    )
    return {"reset_token": reset_token, "message": "Identity verified. Use the reset_token to set a new password."}


@router.post("/forgot-password/reset")
async def forgot_password_reset(
    payload: PasswordReset,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2 — verify identity again and set new password in a single request.
    Accepts the same DOB / security-answer verification as step 1.
    """
    user = await get_user_by_email(payload.email, db)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with that email")

    verified = False
    if payload.date_of_birth and user.date_of_birth:
        if payload.date_of_birth == user.date_of_birth:
            verified = True
    if payload.security_answer and user.security_answer_hash:
        if verify_password(payload.security_answer.strip().lower(), user.security_answer_hash):
            verified = True

    if not verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identity verification failed. Check your date of birth or security answer.",
        )

    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password updated successfully. You can now log in with your new password."}


# ── Admin user management ─────────────────────────────────────────────────

@router.get("/users", response_model=List[UserPublic])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all users — admin only"""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    out = []
    for u in users:
        pub = UserPublic.model_validate(u)
        pub.has_recovery = bool(u.date_of_birth or u.security_answer_hash)
        out.append(pub)
    return out


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Deactivate a user account — admin only"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    user.is_active = False
    await db.commit()
