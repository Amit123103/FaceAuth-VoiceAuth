import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_register_user_validation_error(client: AsyncClient):
    # Test registration with missing fields
    response = await client.post("/api/auth/register", json={
        "username": "testuser",
        "email": "invalid-email"
    })
    assert response.status_code == 422 # Pydantic validation error

@pytest.mark.asyncio
async def test_login_non_existent_user(client: AsyncClient):
    response = await client.post("/api/auth/login", json={
        "username": "nonexistent",
        "password": "somepassword"
    })
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]
