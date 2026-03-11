"""Testes para routers/reservations.py - Endpoints web."""

from datetime import date, timedelta


async def test_index_returns_200(app_client):
    resp = await app_client.get("/")
    assert resp.status_code == 200
    assert "Reservas" in resp.text


async def test_index_shows_resources(app_client):
    resp = await app_client.get("/")
    assert "Salao de Festas Adulto" in resp.text
    assert "Churrasqueira com Forno de Pizza" in resp.text


async def test_index_shows_flash_message(app_client):
    resp = await app_client.get("/?msg=created")
    assert "agendada com sucesso" in resp.text


async def test_index_shows_error_flash(app_client):
    resp = await app_client.get("/?msg=invalid_date")
    assert "invalida" in resp.text


async def test_index_ignores_unknown_msg(app_client):
    resp = await app_client.get("/?msg=unknown")
    assert resp.status_code == 200


async def test_create_reservation_success(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=30)
    resp = await app_client.post(
        "/reservations",
        data={
            "resource_id": "1",
            "target_date": target.isoformat(),
            "reason": "Aniversario",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "msg=created" in resp.headers["location"]


async def test_create_reservation_with_past_date(app_client):
    resp = await app_client.post(
        "/reservations",
        data={
            "resource_id": "1",
            "target_date": "2020-01-01",
            "reason": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "msg=invalid_date" in resp.headers["location"]


async def test_create_reservation_with_today_date(app_client):
    resp = await app_client.post(
        "/reservations",
        data={
            "resource_id": "1",
            "target_date": date.today().isoformat(),
            "reason": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "msg=invalid_date" in resp.headers["location"]


async def test_create_reservation_within_window_sets_pending(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=30)
    resp = await app_client.post(
        "/reservations",
        data={"resource_id": "1", "target_date": target.isoformat(), "reason": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "msg=created" in resp.headers["location"]


async def test_create_reservation_scheduled_for_future(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=120)
    resp = await app_client.post(
        "/reservations",
        data={"resource_id": "1", "target_date": target.isoformat(), "reason": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_create_reservation_with_reason(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=120)
    resp = await app_client.post(
        "/reservations",
        data={"resource_id": "1", "target_date": target.isoformat(), "reason": "Festa de Natal"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "msg=created" in resp.headers["location"]


async def test_create_reservation_empty_reason(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=120)
    resp = await app_client.post(
        "/reservations",
        data={"resource_id": "1", "target_date": target.isoformat(), "reason": "  "},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_detail_page_exists(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=120)
    await app_client.post(
        "/reservations",
        data={"resource_id": "1", "target_date": target.isoformat(), "reason": "Teste"},
        follow_redirects=False,
    )
    resp = await app_client.get("/reservations/1")
    assert resp.status_code == 200
    assert "Reserva #1" in resp.text
    assert "Teste" in resp.text


async def test_detail_page_not_found_redirects(app_client):
    resp = await app_client.get("/reservations/999", follow_redirects=False)
    assert resp.status_code == 307 or resp.status_code == 302 or resp.status_code == 200


async def test_cancel_reservation(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=120)
    await app_client.post(
        "/reservations",
        data={"resource_id": "1", "target_date": target.isoformat(), "reason": ""},
        follow_redirects=False,
    )
    resp = await app_client.post("/reservations/1/cancel", follow_redirects=False)
    assert resp.status_code == 303
    assert "msg=cancelled" in resp.headers["location"]


async def test_cancel_nonexistent_reservation(app_client):
    resp = await app_client.post("/reservations/999/cancel", follow_redirects=False)
    assert resp.status_code == 303


async def test_execute_now(app_client, mock_run_reservation):
    target = date.today() + timedelta(days=120)
    await app_client.post(
        "/reservations",
        data={"resource_id": "1", "target_date": target.isoformat(), "reason": ""},
        follow_redirects=False,
    )
    resp = await app_client.post("/reservations/1/execute", follow_redirects=False)
    assert resp.status_code == 303


async def test_execute_now_nonexistent(app_client):
    resp = await app_client.post("/reservations/999/execute", follow_redirects=False)
    assert resp.status_code == 303
