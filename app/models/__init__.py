"""
app/models/__init__.py — Model registry
Import all models here to ensure they register with SQLAlchemy's metadata.
"""
from app.models.role import Role, Permission, role_permissions, user_roles
from app.models.user import User
from app.models.document import Document, DocumentType, DocumentStatus

__all__ = [
    "Role", "Permission", "role_permissions", "user_roles",
    "User",
    "Document", "DocumentType", "DocumentStatus",
]
