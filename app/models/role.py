"""
app/models/role.py — Role & Permission ORM Models

Tables:
- roles: Defines available roles (admin, analyst, auditor, client)
- permissions: Defines granular permissions (upload, delete, etc.)
- role_permissions: Many-to-many join between roles and permissions
- user_roles: Many-to-many join between users and roles
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, Text,
    ForeignKey, DateTime, UniqueConstraint, Table
)
from sqlalchemy.orm import relationship

from app.db.session import Base


# ─── Association Tables ───────────────────────────────────────────────────────

# Many-to-many: Role ↔ Permission
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-many: User ↔ Role
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


# ─── Role Model ───────────────────────────────────────────────────────────────

class Role(Base):
    """
    Defines a role in the RBAC system.

    Built-in roles: admin, analyst, auditor, client
    """
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    users = relationship("User", secondary=user_roles, back_populates="roles")

    def __repr__(self):
        return f"<Role id={self.id} name={self.name}>"


# ─── Permission Model ─────────────────────────────────────────────────────────

class Permission(Base):
    """
    Granular permission definition.

    Example permissions:
    - document:upload, document:delete, document:view
    - user:manage, role:assign
    - rag:index, rag:search
    """
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    resource = Column(String(50), nullable=False)   # e.g. "document", "user"
    action = Column(String(50), nullable=False)     # e.g. "upload", "delete"

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_resource_action"),
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    def __repr__(self):
        return f"<Permission {self.resource}:{self.action}>"
