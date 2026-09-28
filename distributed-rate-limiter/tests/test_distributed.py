import time
import httpx
import pytest

# When running from host Mac, hit localhost:8000 (Nginx port).
# When running inside Docker app container, hit nginx:80.
BASE_URL = "http://localhost:8000"

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

@pytest.fixture(autouse=True)
def clear_redis():
    """Clear Redis keys before each test so tests start fresh."""
    r.flushall()
    
def test_round_robin_distribution():
    """Verify that Nginx distributes incoming traffic across both app instances."""
    handled_by_instances = set()
    headers = {"Connection": "close"}

    # Use a fresh client and hit the un-rate-limited root route /
    for _ in range(6):
        with httpx.Client(base_url=BASE_URL) as client:
            response = client.get("/", headers=headers)
            assert response.status_code == 200
            data = response.json()
            handled_by_instances.add(data.get("handled_by"))

    assert "app1" in handled_by_instances
    assert "app2" in handled_by_instances


def test_distributed_rate_limiting():
    """
    Verify rate limiting across multiple instances using a unique API key
    so it doesn't pollute other tests.
    """
    unique_key = f"dist_user_{time.time()}"
    headers = {"X-API-Key": unique_key, "Connection": "close"}
    responses = []

    for _ in range(10):
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/api/v1/data", headers=headers)
            responses.append(res.status_code)
            time.sleep(0.05)

    assert responses[:5] == [200, 200, 200, 200, 200]
    assert responses[5:] == [429, 429, 429, 429, 429]