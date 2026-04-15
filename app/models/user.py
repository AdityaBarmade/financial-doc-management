"""
app/models/user.py — User ORM Model

Table: users
- Stores user credentials & profile
- Links to roles via many-to-many (user_roles)
- All passwords stored as bcrypt hashes
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.models.role import user_roles  # Import association table


class User(Base):
    """
    User account model.

    Relationships:
    - roles: Many-to-many with Role (via user_roles junction table)
    - documents: One-to-many with Document (files uploaded by this user)
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    # Profile fields
    company = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    avatar_url = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login = Column(DateTime(timezone=True), nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    documents = relationship("Document", back_populates="uploaded_by_user", lazy="dynamic")

    # ─── Helpers ──────────────────────────────────────────────────────────────
    @property
    def role_names(self) -> list[str]:
        """Return list of role name strings."""
        return [role.name for role in self.roles]

    @property
    def all_permissions(self) -> list[str]:
        """Return flattened list of 'resource:action' permission strings."""
        permissions = set()
        for role in self.roles:
            for perm in role.permissions:
                permissions.add(f"{perm.resource}:{perm.action}")
        return list(permissions)

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return role_name in self.role_names

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if user has a specific resource:action permission."""
        return f"{resource}:{action}" in self.all_permissions

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"
