"""
app/services/auth_service.py — Authentication Business Logic

Handles:
- User registration (validation, password hashing, save to DB)
- Login (credential verification, token generation)
- Token refresh
- Default role/permission seeding on startup
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import hash_password, verify_password, create_token_pair, decode_token
from app.core.exceptions import (
    ConflictException, CredentialsException, NotFoundException, BadRequestException
)
from app.core.logging import get_logger
from app.models.user import User
from app.models.role import Role, Permission
from app.schemas.auth import UserRegisterRequest, LoginRequest

logger = get_logger(__name__)


class AuthService:
    """
    Authentication service - handles all auth business logic.

    Injected with an async DB session per request.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: UserRegisterRequest) -> User:
        """
        Register a new user.

        Steps:
        1. Check if email already exists
        2. Hash password
        3. Create User record
        4. Assign default 'client' role
        5. Return user

        Raises:
            ConflictException: If email already registered
        """
        # Check for existing email
        stmt = select(User).where(User.email == data.email.lower())
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise ConflictException(f"Email '{data.email}' is already registered")

        # Create user
        user = User(
            email=data.email.lower().strip(),
            full_name=data.full_name.strip(),
            hashed_password=hash_password(data.password),
            company=data.company,
            phone=data.phone,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()  # Get user.id without committing

        # Assign default 'client' role
        client_role = await self._get_role_by_name("client")
        if client_role:
            user.roles.append(client_role)

        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"New user registered: {user.email} (id={user.id})")
        return user

    async def login(self, data: LoginRequest) -> dict:
        """
        Authenticate a user and return JWT tokens.

        Returns:
            dict with access_token, refresh_token, user info
        Raises:
            CredentialsException: If credentials are invalid
        """
        # Load user with roles
        stmt = (
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.email == data.email.lower())
        )
        user = (await self.db.execute(stmt)).scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise CredentialsException("Invalid email or password")

        if not user.is_active:
            raise CredentialsException("Account is deactivated. Contact support.")

        # Update last login timestamp
        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()

        # Generate token pair
        token_pair = create_token_pair(
            user_id=user.id,
            email=user.email,
            roles=user.role_names,
        )

        logger.info(f"User logged in: {user.email}")
        return {
            "access_token": token_pair.access_token,
            "refresh_token": token_pair.refresh_token,
            "token_type": "bearer",
            "expires_in": token_pair.expires_in,
            "user_id": user.id,
            "email": user.email,
            "roles": user.role_names,
        }

    async def refresh_token(self, refresh_token: str) -> dict:
        """
        Issue a new access token using a refresh token.

        Raises:
            CredentialsException: If refresh token is invalid
        """
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise CredentialsException("Invalid or expired refresh token")

        if payload.get("type") != "refresh":
            raise CredentialsException("Not a refresh token")

        user_id = int(payload.get("sub", 0))
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        user = (await self.db.execute(stmt)).scalar_one_or_none()

        if not user or not user.is_active:
            raise CredentialsException("User not found or inactive")

        from app.core.security import create_access_token
        new_token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "roles": user.role_names,
        })

        from app.core.config import settings
        return {
            "access_token": new_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def _get_role_by_name(self, name: str) -> Optional[Role]:
        """Look up a role by name."""
        result = await self.db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    @staticmethod
    async def seed_default_roles(db: AsyncSession):
        """
        Create default roles and permissions on first startup.
        Idempotent — safe to call multiple times.
        """
        # ─── Permissions ──────────────────────────────────────────────────────
        default_permissions = [
            ("document", "upload", "Upload financial documents"),
            ("document", "view", "View documents"),
            ("document", "edit", "Edit document metadata"),
            ("document", "delete", "Delete documents"),
            ("document", "export", "Export/download documents"),
            ("user", "manage", "Manage users"),
            ("role", "assign", "Assign roles to users"),
            ("rag", "index", "Index documents in vector store"),
            ("rag", "search", "Perform semantic search"),
            ("rag", "context", "Retrieve document context"),
            ("admin", "all", "Full system access"),
        ]

        perm_objects = {}
        for resource, action, desc in default_permissions:
            name = f"{resource}:{action}"
            stmt = select(Permission).where(Permission.name == name)
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if not existing:
                perm = Permission(name=name, resource=resource, action=action, description=desc)
                db.add(perm)
                await db.flush()
                perm_objects[name] = perm
            else:
                perm_objects[name] = existing

        # ─── Roles ────────────────────────────────────────────────────────────
        role_definitions = {
            "admin": {
                "description": "Full system administrator access",
                "permissions": list(perm_objects.keys()),
            },
            "analyst": {
                "description": "Can upload and edit financial documents",
                "permissions": [
                    "document:upload", "document:view", "document:edit",
                    "document:export", "rag:index", "rag:search", "rag:context",
                ],
            },
            "auditor": {
                "description": "Can review and audit documents",
                "permissions": [
                    "document:view", "document:export",
                    "rag:search", "rag:context",
                ],
            },
            "client": {
                "description": "Read-only access to documents",
                "permissions": ["document:view", "rag:search"],
            },
        }

        for role_name, role_data in role_definitions.items():
            stmt = select(Role).where(Role.name == role_name)
            existing_role = (await db.execute(stmt)).scalar_one_or_none()
            if not existing_role:
                role = Role(
                    name=role_name,
                    description=role_data["description"],
                )
                # Attach permissions
                for perm_name in role_data["permissions"]:
                    if perm_name in perm_objects:
                        role.permissions.append(perm_objects[perm_name])
                db.add(role)
                logger.info(f"Created default role: {role_name}")

        await db.commit()
        logger.info("✅ Default roles and permissions seeded")
