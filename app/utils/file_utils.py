"""
app/utils/file_utils.py — File Handling Utilities

Helper functions for:
- Validating file extensions and sizes
- Generating unique file names
- Human-readable file size formatting
"""

import os
import uuid
import mimetypes
from pathlib import Path


def generate_unique_filename(original_filename: str) -> str:
    """
    Generate a UUID-based unique filename preserving the original extension.

    Example: "Q4-Report.pdf" → "f47ac10b-58cc-4372-a567-0e02b2c3d479.pdf"
    """
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4()}{ext}"


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def get_mime_type(filename: str) -> str:
    """Detect MIME type from filename."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def ensure_directory(path: str) -> str:
    """Create directory if it doesn't exist. Returns the path."""
    os.makedirs(path, exist_ok=True)
    return path


def safe_delete_file(file_path: str) -> bool:
    """
    Delete a file safely without raising exceptions.

    Returns:
        True if deleted, False if file didn't exist or error occurred
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except OSError:
        return False


def get_file_extension(filename: str) -> str:
    """Extract lowercase file extension including the dot."""
    return Path(filename).suffix.lower()
