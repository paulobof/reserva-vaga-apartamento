"""Testes para main.py - Health check, favicon, init_db."""


async def test_health_check_returns_json(app_client):
    resp = await app_client.get("/health")
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert "version" in data
    assert "checks" in data


async def test_health_check_has_db_check(app_client):
    resp = await app_client.get("/health")
    data = resp.json()
    assert "database" in data["checks"]


async def test_health_check_has_scheduler_check(app_client):
    resp = await app_client.get("/health")
    data = resp.json()
    assert "scheduler" in data["checks"]


async def test_favicon_returns_204(app_client):
    resp = await app_client.get("/favicon.ico")
    assert resp.status_code == 204


async def test_security_txt_returns_204(app_client):
    resp = await app_client.get("/security.txt")
    assert resp.status_code == 204


async def test_well_known_security_txt_returns_204(app_client):
    resp = await app_client.get("/.well-known/security.txt")
    assert resp.status_code == 204
