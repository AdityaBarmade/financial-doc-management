"""
app/schemas/auth.py — Authentication Pydantic Schemas

Handles request/response validation for:
- User registration
- Login
- Token refresh
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
import re


class UserRegisterRequest(BaseModel):
    """Request body for POST /auth/register."""
    email: EmailStr
    full_name: str
    password: str
    company: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce password complexity requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john.doe@company.com",
                "full_name": "John Doe",
                "password": "SecurePass123",
                "company": "Acme Corp",
                "phone": "+1-555-0100",
            }
        }
    )


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""
    email: EmailStr
    password: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john.doe@company.com",
                "password": "SecurePass123",
            }
        }
    )


class TokenResponse(BaseModel):
    """Response from login containing JWT tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    user_id: int
    email: str
    roles: list[str]


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh."""
    refresh_token: str


class UserResponse(BaseModel):
    """Public user profile data returned in responses."""
    id: int
    email: str
    full_name: str
    company: Optional[str] = None
    is_active: bool
    roles: list[str] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
