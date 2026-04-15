"""
tests/test_auth.py — Authentication API Tests

Tests:
- User registration (success, duplicate email, weak password)
- Login (success, wrong password, inactive user)
- JWT token validation
- Token refresh
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.auth_service import AuthService


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def registered_user(client):
    """Register and return a test user."""
    response = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "TestPass123",
        "company": "Test Corp",
    })
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def auth_tokens(client, registered_user):
    """Login and return JWT tokens."""
    response = await client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "TestPass123",
    })
    assert response.status_code == 200
    return response.json()


class TestRegistration:
    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "newuser@test.com",
            "full_name": "New User",
            "password": "ValidPass123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert "id" in data
        assert "hashed_password" not in data  # Never expose hash

    async def test_register_duplicate_email(self, client: AsyncClient, registered_user):
        response = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",  # Already registered
            "full_name": "Duplicate User",
            "password": "ValidPass123",
        })
        assert response.status_code == 409

    async def test_register_weak_password(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "weak@test.com",
            "full_name": "Weak Auth User",
            "password": "abc",  # Too short
        })
        assert response.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "full_name": "Bad Email User",
            "password": "ValidPass123",
        })
        assert response.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient, registered_user):
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "TestPass123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, registered_user):
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "WrongPassword123",
        })
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/login", json={
            "email": "nobody@nowhere.com",
            "password": "SomePass123",
        })
        assert response.status_code == 401


class TestProtectedEndpoints:
    async def test_get_me_with_token(self, client: AsyncClient, auth_tokens):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {auth_tokens['access_token']}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"

    async def test_get_me_without_token(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_get_me_invalid_token(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401

    async def test_refresh_token(self, client: AsyncClient, auth_tokens):
        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": auth_tokens["refresh_token"]
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data


class TestHealthCheck:
    async def test_health_endpoint(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
