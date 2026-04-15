"""
app/services/user_service.py — User & Role Management Business Logic

Handles:
- Fetching user profiles
- Assigning/revoking roles
- Listing user roles and permissions
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException, ConflictException, BadRequestException
from app.core.logging import get_logger
from app.models.user import User
from app.models.role import Role

logger = get_logger(__name__)


class UserService:
    """Business logic for user and role management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_id(self, user_id: int) -> User:
        """
        Load a user with their roles and permissions.

        Raises:
            NotFoundException: If user doesn't exist
        """
        stmt = (
            select(User)
            .options(
                selectinload(User.roles).selectinload(Role.permissions)
            )
            .where(User.id == user_id)
        )
        user = (await self.db.execute(stmt)).scalar_one_or_none()

        if not user:
            raise NotFoundException("User")

        return user

    async def assign_role(self, user_id: int, role_name: str) -> User:
        """
        Assign a role to a user.

        Raises:
            NotFoundException: If user or role not found
            ConflictException: If user already has the role
        """
        user = await self.get_user_by_id(user_id)

        # Load role
        role_stmt = select(Role).where(Role.name == role_name, Role.is_active == True)
        role = (await self.db.execute(role_stmt)).scalar_one_or_none()

        if not role:
            raise NotFoundException(f"Role '{role_name}'")

        # Check if already assigned
        if role in user.roles:
            raise ConflictException(f"User already has role '{role_name}'")

        user.roles.append(role)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"Assigned role '{role_name}' to user {user.email}")
        return user

    async def revoke_role(self, user_id: int, role_name: str) -> User:
        """
        Remove a role from a user.

        Raises:
            NotFoundException: If user or role not found
            BadRequestException: If user doesn't have the role
        """
        user = await self.get_user_by_id(user_id)

        role_to_remove = None
        for role in user.roles:
            if role.name == role_name:
                role_to_remove = role
                break

        if not role_to_remove:
            raise BadRequestException(f"User does not have role '{role_name}'")

        user.roles.remove(role_to_remove)
        await self.db.commit()

        logger.info(f"Revoked role '{role_name}' from user {user.email}")
        return user

    async def get_user_roles(self, user_id: int) -> dict:
        """Get all roles assigned to a user."""
        user = await self.get_user_by_id(user_id)

        return {
            "user_id": user_id,
            "email": user.email,
            "roles": [
                {
                    "id": role.id,
                    "name": role.name,
                    "description": role.description,
                }
                for role in user.roles
            ],
        }

    async def get_user_permissions(self, user_id: int) -> dict:
        """Get all permissions for a user (via their roles)."""
        user = await self.get_user_by_id(user_id)

        permissions_by_role = {}
        for role in user.roles:
            permissions_by_role[role.name] = [
                f"{perm.resource}:{perm.action}"
                for perm in role.permissions
            ]

        return {
            "user_id": user_id,
            "email": user.email,
            "all_permissions": user.all_permissions,
            "permissions_by_role": permissions_by_role,
        }

    async def list_users(self, page: int = 1, page_size: int = 20) -> dict:
        """List all users with pagination."""
        from sqlalchemy import func

        # Count
        count_stmt = select(func.count(User.id))
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        users = (await self.db.execute(stmt)).scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": users,
        }
