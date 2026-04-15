"""
app/core/exceptions.py — Custom Exception Classes

Defines domain-specific HTTP exceptions with clear messages.
All exceptions map to appropriate HTTP status codes.
"""

from fastapi import HTTPException, status


class CredentialsException(HTTPException):
    """Raised when JWT token is invalid or missing."""
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(HTTPException):
    """Raised when user lacks required role/permission."""
    def __init__(self, detail: str = "You don't have permission to perform this action"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundException(HTTPException):
    """Raised when a requested resource does not exist."""
    def __init__(self, resource: str = "Resource"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found",
        )


class ConflictException(HTTPException):
    """Raised when a resource already exists (e.g., duplicate email)."""
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class BadRequestException(HTTPException):
    """Raised for invalid input or business rule violations."""
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class FileTooLargeException(HTTPException):
    """Raised when uploaded file exceeds size limit."""
    def __init__(self, max_mb: int):
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the {max_mb}MB limit",
        )


class UnsupportedFileTypeException(HTTPException):
    """Raised when file extension is not in the allowed list."""
    def __init__(self, extension: str, allowed: list[str]):
        super().__init__(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{extension}' not supported. Allowed: {', '.join(allowed)}",
        )


class RAGException(HTTPException):
    """Raised when RAG/vector operations fail."""
    def __init__(self, detail: str = "RAG operation failed"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
