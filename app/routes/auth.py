"""
app/routes/auth.py — Authentication Endpoints

POST /auth/register  - Register new user
POST /auth/login     - Login and get JWT tokens
POST /auth/refresh   - Refresh access token
GET  /auth/me        - Get current user profile
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user_with_roles
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest, LoginRequest, TokenResponse,
    RefreshTokenRequest, UserResponse
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="""
Register a new user account.

**Default role**: All new users are assigned the `client` role.
To assign other roles, use `POST /users/assign-role` (requires admin).

**Password requirements**:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
""",
)
async def register(
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    service = AuthService(db)
    user = await service.register(data)

    # Seed default roles on first run (idempotent)
    await AuthService.seed_default_roles(db)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        company=user.company,
        is_active=user.is_active,
        roles=user.role_names,
        created_at=user.created_at,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and get JWT tokens",
    description="""
Authenticate with email and password.

Returns both **access token** (short-lived, 30 min) and **refresh token** (7 days).

Include the access token in subsequent requests:
```
Authorization: Bearer <access_token>
```
""",
)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    service = AuthService(db)
    result = await service.login(data)
    return TokenResponse(**result)


@router.post(
    "/refresh",
    summary="Refresh access token",
    description="Use a valid refresh token to get a new access token.",
)
async def refresh_token(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.refresh_token(data.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user_with_roles),
) -> UserResponse:
    """Return the profile of the currently authenticated user."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        company=current_user.company,
        is_active=current_user.is_active,
        roles=current_user.role_names,
        created_at=current_user.created_at,
    )


@router.post(
    "/seed-roles",
    summary="Seed default roles and permissions",
    description="Initialize default roles (admin, analyst, auditor, client) and permissions. Safe to call multiple times.",
    status_code=status.HTTP_200_OK,
)
async def seed_roles(db: AsyncSession = Depends(get_db)):
    """Seed default roles and permissions into the database."""
    await AuthService.seed_default_roles(db)
    return {"message": "Default roles and permissions seeded successfully"}
