"""
app/routes/roles.py — Role Management Endpoints

POST /roles/create          - Create a new role (admin only)
GET  /roles                 - List all roles
GET  /roles/{role_id}       - Get role details
DELETE /roles/{role_id}     - Deactivate a role (admin only)
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.auth.dependencies import require_roles, get_current_user_with_roles
from app.models.role import Role
from app.models.user import User
from app.schemas.rag import RoleCreateRequest, RoleResponse
from app.core.exceptions import NotFoundException, ConflictException

router = APIRouter()


@router.post(
    "/create",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new role",
    description="Create a custom role. **Admin only.**",
)
async def create_role(
    data: RoleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
) -> RoleResponse:
    # Check for duplicate
    existing = (await db.execute(select(Role).where(Role.name == data.name))).scalar_one_or_none()
    if existing:
        raise ConflictException(f"Role '{data.name}' already exists")

    role = Role(name=data.name, description=data.description)
    db.add(role)
    await db.commit()
    await db.refresh(role)

    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_active=role.is_active,
        permissions=[],
    )


@router.get(
    "",
    summary="List all roles",
    description="Return all available roles with their permissions.",
)
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_roles),
):
    from sqlalchemy.orm import selectinload
    from app.models.role import Permission

    stmt = select(Role).options(selectinload(Role.permissions)).where(Role.is_active == True)
    roles = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "is_active": role.is_active,
            "permissions": [f"{p.resource}:{p.action}" for p in role.permissions],
        }
        for role in roles
    ]


@router.get(
    "/{role_id}",
    summary="Get role by ID",
)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_roles),
):
    from sqlalchemy.orm import selectinload
    stmt = (
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role_id)
    )
    role = (await db.execute(stmt)).scalar_one_or_none()

    if not role:
        raise NotFoundException("Role")

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_active": role.is_active,
        "permissions": [f"{p.resource}:{p.action}" for p in role.permissions],
    }


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate a role",
    description="Soft-deactivate a role. **Admin only.**",
)
async def deactivate_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()

    if not role:
        raise NotFoundException("Role")

    # Prevent deactivating system roles
    protected_roles = ["admin", "analyst", "auditor", "client"]
    if role.name in protected_roles:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException(f"Cannot deactivate built-in role '{role.name}'")

    role.is_active = False
    await db.commit()

    return {"message": f"Role '{role.name}' deactivated successfully"}
