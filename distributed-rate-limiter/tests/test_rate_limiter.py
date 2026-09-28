import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from main import app, r

@pytest.fixture(autouse=True)
def clear_redis():
    """Clear Redis keys before each test so tests start fresh."""
    r.flushall()

@pytest.fixture
async def client():
    """Create an async HTTP client connected directly to FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# TEST 1 & 2: Under the Limit & Over the Limit
async def test_rate_limiter_under_and_over_limit(client: AsyncClient):
    headers = {"X-API-Key": "test_user_under_over"}

    # 1. Send 5 requests (the limit) -> All should be 200 OK
    for i in range(5):
        response = await client.get("/api/v1/data", headers=headers)
        assert response.status_code == 200, f"Request {i+1} failed"
        assert response.headers["X-RateLimit-Remaining"] == str(5 - (i + 1))

    # 2. Send 6th request (over limit) -> Should be 429 Too Many Requests
    response_blocked = await client.get("/api/v1/data", headers=headers)
    assert response_blocked.status_code == 429
    assert response_blocked.json() == {"error": "Too Many Requests"}
    assert response_blocked.headers["Retry-After"] == "10"


# TEST 3: Window Reset after Expiry
async def test_rate_limiter_window_reset(client: AsyncClient):
    headers = {"X-API-Key": "test_user_reset"}

    # Exhaust all 5 allowed requests
    for _ in range(5):
        await client.get("/api/v1/data", headers=headers)

    # 6th request is blocked
    blocked = await client.get("/api/v1/data", headers=headers)
    assert blocked.status_code == 429

    # Wait 10.1 seconds for the rolling window to pass
    await asyncio.sleep(10.1)

    # Request after window expires should succeed again
    allowed_again = await client.get("/api/v1/data", headers=headers)
    assert allowed_again.status_code == 200


# TEST 4: Key Isolation (User A does not affect User B)
async def test_rate_limiter_key_isolation(client: AsyncClient):
    user_a_headers = {"X-API-Key": "user_a"}
    user_b_headers = {"X-API-Key": "user_b"}

    # Exhaust limit for User A
    for _ in range(5):
        await client.get("/api/v1/data", headers=user_a_headers)

    # User A is blocked on 6th request
    user_a_blocked = await client.get("/api/v1/data", headers=user_a_headers)
    assert user_a_blocked.status_code == 429

    # User B should STILL be allowed because they have a separate key bucket
    user_b_allowed = await client.get("/api/v1/data", headers=user_b_headers)
    assert user_b_allowed.status_code == 200
    assert user_b_allowed.headers["X-RateLimit-Remaining"] == "4"