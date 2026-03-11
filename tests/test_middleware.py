"""Testes para middleware.py - ObservabilityMiddleware."""


async def test_middleware_returns_correlation_id(app_client):
    resp = await app_client.get("/health")
    assert "x-correlation-id" in resp.headers


async def test_middleware_returns_response_time(app_client):
    resp = await app_client.get("/health")
    assert "x-response-time" in resp.headers
    assert resp.headers["x-response-time"].endswith("ms")


async def test_middleware_preserves_correlation_id(app_client):
    resp = await app_client.get("/health", headers={"X-Correlation-ID": "test-cid-123"})
    assert resp.headers["x-correlation-id"] == "test-cid-123"


async def test_middleware_generates_correlation_id(app_client):
    resp = await app_client.get("/health")
    cid = resp.headers.get("x-correlation-id")
    assert cid is not None
    assert len(cid) > 0
