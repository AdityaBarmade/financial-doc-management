"""
app/auth/dependencies.py — FastAPI Auth Dependencies

Provides reusable dependency functions:
- get_current_user: Extracts & validates JWT, returns User
- require_roles: Role-based access guard factory
- require_permission: Permission-based guard factory
"""

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional

from app.core.security import decode_token
from app.core.exceptions import CredentialsException, ForbiddenException
from app.db.session import get_db
from app.models.user import User

# HTTP Bearer token extractor
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency: Extract JWT from Authorization header and load User from DB.

    Raises:
        CredentialsException: If token is missing, invalid, or user not found
    """
    if not credentials:
        raise CredentialsException("Authorization header missing")

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise CredentialsException("Invalid or expired token")

    # Validate token type
    if payload.get("type") != "access":
        raise CredentialsException("Refresh tokens cannot be used for API access")

    user_id = payload.get("sub")
    if not user_id:
        raise CredentialsException("Token payload missing user ID")

    # Load user from DB with roles eagerly loaded
    from app.models.role import Role
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise CredentialsException("User not found")

    if not user.is_active:
        raise CredentialsException("User account is deactivated")

    return user


async def get_current_user_with_roles(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Like get_current_user but ensures roles and permissions are loaded.
    """
    if not credentials:
        raise CredentialsException("Authorization header missing")

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise CredentialsException("Invalid or expired token")

    if payload.get("type") != "access":
        raise CredentialsException("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise CredentialsException("Token payload missing user ID")

    # Eagerly load roles → permissions hierarchy
    from sqlalchemy.orm import selectinload
    from app.models.role import Role, Permission

    result = await db.execute(
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions)
        )
        .where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise CredentialsException("User not found or inactive")

    return user


def require_roles(*roles: str):
    """
    Factory function that creates a dependency requiring specific roles.

    Usage:
        @router.get("/admin-only")
        async def endpoint(user = Depends(require_roles("admin"))):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_user_with_roles),
    ) -> User:
        user_roles = current_user.role_names
        if not any(role in user_roles for role in roles):
            raise ForbiddenException(
                f"Required roles: {', '.join(roles)}. Your roles: {', '.join(user_roles) or 'none'}"
            )
        return current_user
    return role_checker


def require_permission(resource: str, action: str):
    """
    Factory function that creates a dependency requiring a specific permission.

    Usage:
        @router.delete("/{id}")
        async def endpoint(user = Depends(require_permission("document", "delete"))):
            ...
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user_with_roles),
    ) -> User:
        # Admins bypass all permission checks
        if "admin" in current_user.role_names:
            return current_user

        if not current_user.has_permission(resource, action):
            raise ForbiddenException(
                f"Permission required: {resource}:{action}"
            )
        return current_user
    return permission_checker
