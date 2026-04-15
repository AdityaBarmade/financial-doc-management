"""
app/routes/users.py — User Management Endpoints

GET  /users                     - List all users (admin only)
GET  /users/{id}                - Get user profile
POST /users/assign-role         - Assign role to user (admin only)
POST /users/revoke-role         - Revoke role from user (admin only)
GET  /users/{id}/roles          - Get user's roles
GET  /users/{id}/permissions    - Get user's permissions
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import require_roles, get_current_user_with_roles
from app.models.user import User
from app.schemas.rag import AssignRoleRequest
from app.schemas.auth import UserResponse
from app.services.user_service import UserService

router = APIRouter()


@router.get(
    "",
    summary="List all users",
    description="Paginated list of all registered users. **Admin only.**",
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    service = UserService(db)
    result = await service.list_users(page=page, page_size=page_size)

    # Serialize users
    result["items"] = [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            company=u.company,
            is_active=u.is_active,
            roles=u.role_names,
            created_at=u.created_at,
        )
        for u in result["items"]
    ]
    return result


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_roles),
) -> UserResponse:
    # Users can view their own profile; admins can view anyone
    if current_user.id != user_id and "admin" not in current_user.role_names:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException("You can only view your own profile")

    service = UserService(db)
    user = await service.get_user_by_id(user_id)

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
    "/assign-role",
    status_code=status.HTTP_200_OK,
    summary="Assign a role to a user",
    description="Assign a role to a user. **Admin only.**",
)
async def assign_role(
    data: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    service = UserService(db)
    user = await service.assign_role(data.user_id, data.role_name)
    return {
        "message": f"Role '{data.role_name}' assigned to user {user.email}",
        "user_id": user.id,
        "roles": user.role_names,
    }


@router.post(
    "/revoke-role",
    status_code=status.HTTP_200_OK,
    summary="Revoke a role from a user",
    description="Remove a role assignment. **Admin only.**",
)
async def revoke_role(
    data: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    service = UserService(db)
    user = await service.revoke_role(data.user_id, data.role_name)
    return {
        "message": f"Role '{data.role_name}' revoked from user {user.email}",
        "user_id": user.id,
        "roles": user.role_names,
    }


@router.get(
    "/{user_id}/roles",
    summary="Get user's roles",
    description="List all roles assigned to a user.",
)
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_roles),
):
    # Users can view their own roles; admins can view anyone
    if current_user.id != user_id and "admin" not in current_user.role_names:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException("You can only view your own roles")

    service = UserService(db)
    return await service.get_user_roles(user_id)


@router.get(
    "/{user_id}/permissions",
    summary="Get user's permissions",
    description="List all permissions a user has (via their roles).",
)
async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_roles),
):
    if current_user.id != user_id and "admin" not in current_user.role_names:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException("You can only view your own permissions")

    service = UserService(db)
    return await service.get_user_permissions(user_id)
