"""Testes para services/icondominio.py - Core API client."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.models import AttemptLog, Reservation
from app.services.icondominio import ICondominioClient, _extract_attr

# ===== Testes unitarios para _extract_attr =====


def test_extract_attr_double_quotes():
    assert _extract_attr('name="foo" value="bar"', "value") == "bar"


def test_extract_attr_single_quotes():
    assert _extract_attr("name='foo' value='bar'", "name") == "foo"


def test_extract_attr_not_found():
    assert _extract_attr('name="foo"', "value") is None


def test_extract_attr_case_insensitive():
    assert _extract_attr('Name="foo"', "name") == "foo"


def test_extract_attr_empty_value():
    assert _extract_attr('name="test" value=""', "value") == ""


def test_extract_attr_with_type():
    assert _extract_attr('type="hidden" name="field1"', "type") == "hidden"


# ===== Testes para ICondominioClient =====


async def test_client_init():
    client = ICondominioClient()
    assert client.client is None


async def test_ensure_client_creates_new():
    client = ICondominioClient()
    http_client = await client._ensure_client()
    assert http_client is not None
    assert not http_client.is_closed
    await client.close()


async def test_ensure_client_reuses_existing():
    client = ICondominioClient()
    first = await client._ensure_client()
    second = await client._ensure_client()
    assert first is second
    await client.close()


async def test_close_client():
    client = ICondominioClient()
    await client._ensure_client()
    await client.close()
    assert client.client.is_closed


async def test_close_without_client():
    client = ICondominioClient()
    # Nao deve levantar excecao
    await client.close()


async def test_login_success():
    client = ICondominioClient()
    mock_response = httpx.Response(
        200,
        json={"NIU": "12345", "Token": "abc-token"},
        request=httpx.Request("POST", "http://test"),
    )

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        niu, token = await client.login()
        assert niu == "12345"
        assert token == "abc-token"  # noqa: S105


async def test_login_failure_no_niu():
    client = ICondominioClient()
    mock_response = httpx.Response(
        200,
        json={"Error": "Invalid credentials"},
        request=httpx.Request("POST", "http://test"),
    )

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        with pytest.raises(RuntimeError, match="Login failed"):
            await client.login()


async def test_redirect_success():
    client = ICondominioClient()
    mock_response = httpx.Response(
        200,
        json={"URL": "https://www.icondominio.com.br/auth/token123"},
        request=httpx.Request("POST", "http://test"),
    )

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        url = await client.redirect("12345", "abc-token")
        assert url == "https://www.icondominio.com.br/auth/token123"


async def test_redirect_with_url_key():
    """Testa resposta com chave 'Url' ao inves de 'URL'."""
    client = ICondominioClient()
    mock_response = httpx.Response(
        200,
        json={"Url": "https://example.com/auth"},
        request=httpx.Request("POST", "http://test"),
    )

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        url = await client.redirect("12345", "token")
        assert url == "https://example.com/auth"


async def test_redirect_failure():
    client = ICondominioClient()
    mock_response = httpx.Response(
        200,
        json={"Error": "No URL"},
        request=httpx.Request("POST", "http://test"),
    )

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        with pytest.raises(RuntimeError, match="Redirect failed"):
            await client.redirect("12345", "token")


async def test_authenticate_follows_redirects():
    client = ICondominioClient()

    redirect_cookies = httpx.Cookies()
    redirect_cookies.set("session", "abc123")
    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "https://www.icondominio.com.br/next"}
    redirect_resp.cookies = redirect_cookies

    final_cookies = httpx.Cookies()
    final_cookies.set("auth", "xyz")
    final_resp = MagicMock()
    final_resp.status_code = 200
    final_resp.cookies = final_cookies

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[redirect_resp, final_resp])
        mock_ensure.return_value = mock_http

        await client.authenticate("https://example.com/auth")
        assert mock_http.get.call_count == 2


async def test_authenticate_handles_relative_redirect():
    client = ICondominioClient()

    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "/dashboard"}
    redirect_resp.cookies = httpx.Cookies()

    final_resp = MagicMock()
    final_resp.status_code = 200
    final_resp.cookies = httpx.Cookies()

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[redirect_resp, final_resp])
        mock_ensure.return_value = mock_http

        await client.authenticate("https://www.icondominio.com.br/start")
        second_call = mock_http.get.call_args_list[1]
        assert second_call[0][0] == "https://www.icondominio.com.br/dashboard"


async def test_warmup_calls_both_endpoints():
    client = ICondominioClient()
    mock_response = httpx.Response(200, text="OK", request=httpx.Request("GET", "http://test"))

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        await client.warmup(httpx.Cookies(), 2564)
        assert mock_http.get.call_count == 2


async def test_get_condicao_available():
    client = ICondominioClient()
    html = """
    <form>
        <input type="hidden" name="__RequestVerificationToken" value="token123">
        <input type="hidden" name="Data" value="13-06-2026">
        <input type="hidden" name="RecursoDesc" value="SAL&#195;O">
        <input type="checkbox" name="Concordo" value="true">
    </form>
    """
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.url = "http://test/Reservas/Condicao"

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        available, fields = await client.get_condicao(
            httpx.Cookies(), date(2026, 6, 13), 2564, 9894
        )
        assert available is True
        assert "__RequestVerificationToken" in fields
        assert fields["__RequestVerificationToken"] == "token123"
        assert fields["Concordo"] == "on"
        # HTML entities should be unescaped
        assert "&#195;" not in fields.get("RecursoDesc", "")


async def test_get_condicao_unavailable_redirect():
    client = ICondominioClient()
    mock_response = MagicMock()
    mock_response.text = ""
    mock_response.url = "http://test/Reservas/ReservaCancelada"

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        available, fields = await client.get_condicao(
            httpx.Cookies(), date(2026, 6, 13), 2564, 9894
        )
        assert available is False
        assert fields == {}


async def test_get_condicao_unavailable_text():
    client = ICondominioClient()
    mock_response = MagicMock()
    mock_response.text = "<p>Esta data não está disponível para reserva.</p>"
    mock_response.url = "http://test/Reservas/Condicao"

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        available, _fields = await client.get_condicao(
            httpx.Cookies(), date(2026, 6, 13), 2564, 9894
        )
        assert available is False


async def test_get_condicao_no_fields():
    client = ICondominioClient()
    mock_response = MagicMock()
    mock_response.text = "<p>Pagina sem campos</p>"
    mock_response.url = "http://test/Reservas/Condicao"

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        available, fields = await client.get_condicao(
            httpx.Cookies(), date(2026, 6, 13), 2564, 9894
        )
        assert available is False
        assert fields == {}


async def test_submit_success():
    client = ICondominioClient()
    html = "<h1>Reserva agendada com sucesso!</h1>"
    mock_response = httpx.Response(200, text=html, request=httpx.Request("POST", "http://test"))

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        success, snippet = await client.submit(httpx.Cookies(), {"field": "value"})
        assert success is True
        assert "sucesso" in snippet.lower()


async def test_submit_failure():
    client = ICondominioClient()
    html = "<h1>Erro ao processar reserva</h1>"
    mock_response = httpx.Response(200, text=html, request=httpx.Request("POST", "http://test"))

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        success, _snippet = await client.submit(httpx.Cookies(), {"field": "value"})
        assert success is False


async def test_execute_reservation_success(db, seed_resources):
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation, ["resource"])

    client = ICondominioClient()

    with (
        patch.object(client, "login", return_value=("niu", "token")),
        patch.object(client, "redirect", return_value="https://auth-url"),
        patch.object(client, "authenticate", return_value=httpx.Cookies()),
        patch.object(client, "warmup"),
        patch.object(client, "get_condicao", return_value=(True, {"f": "v"})),
        patch.object(client, "submit", return_value=(True, "Reserva agendada com sucesso")),
    ):
        success = await client.execute_reservation(db, reservation, reservation.resource)

    assert success is True
    assert reservation.status == "success"
    assert reservation.attempt_count == 1


async def test_execute_reservation_auth_failure(db, seed_resources):
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation, ["resource"])

    client = ICondominioClient()

    with patch.object(client, "login", side_effect=RuntimeError("Login failed")):
        success = await client.execute_reservation(db, reservation, reservation.resource)

    assert success is False
    assert reservation.status == "failed"
    assert "Auth failed" in reservation.result_message


async def test_execute_reservation_retries_on_unavailable(db, seed_resources):
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation, ["resource"])

    client = ICondominioClient()
    condicao_calls = [
        (False, {}),
        (False, {}),
        (True, {"field": "value"}),
    ]

    with (
        patch.object(client, "login", return_value=("niu", "token")),
        patch.object(client, "redirect", return_value="https://auth-url"),
        patch.object(client, "authenticate", return_value=httpx.Cookies()),
        patch.object(client, "warmup"),
        patch.object(client, "get_condicao", side_effect=condicao_calls),
        patch.object(client, "submit", return_value=(True, "Sucesso")),
        patch("app.services.icondominio.asyncio.sleep"),
    ):
        success = await client.execute_reservation(db, reservation, reservation.resource)

    assert success is True
    assert reservation.attempt_count == 3


async def test_execute_reservation_fails_after_max_attempts(db, seed_resources):
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation, ["resource"])

    client = ICondominioClient()

    with (
        patch.object(client, "login", return_value=("niu", "token")),
        patch.object(client, "redirect", return_value="https://auth-url"),
        patch.object(client, "authenticate", return_value=httpx.Cookies()),
        patch.object(client, "warmup"),
        patch.object(client, "get_condicao", return_value=(False, {})),
        patch("app.services.icondominio.asyncio.sleep"),
        patch("app.services.icondominio.MAX_ATTEMPTS", 3),
    ):
        success = await client.execute_reservation(db, reservation, reservation.resource)

    assert success is False
    assert reservation.status == "failed"
    assert "3 tentativas" in reservation.result_message


async def test_log_attempt_persists(db, sample_reservation):
    client = ICondominioClient()

    await client._log_attempt(db, sample_reservation, 1, "auth", True, snippet="Login OK")

    result = await db.execute(
        select(AttemptLog).where(AttemptLog.reservation_id == sample_reservation.id)
    )
    log = result.scalar_one()
    assert log.step == "auth"
    assert log.success is True
    assert log.response_snippet == "Login OK"


async def test_log_attempt_with_error(db, sample_reservation):
    client = ICondominioClient()

    await client._log_attempt(db, sample_reservation, 1, "condicao", False, error="Timeout")

    result = await db.execute(
        select(AttemptLog).where(AttemptLog.reservation_id == sample_reservation.id)
    )
    log = result.scalar_one()
    assert log.success is False
    assert log.error_message == "Timeout"


async def test_log_attempt_truncates_snippet(db, sample_reservation):
    client = ICondominioClient()
    long_snippet = "x" * 600

    await client._log_attempt(db, sample_reservation, 1, "conclusao", True, snippet=long_snippet)

    result = await db.execute(
        select(AttemptLog).where(AttemptLog.reservation_id == sample_reservation.id)
    )
    log = result.scalar_one()
    assert len(log.response_snippet) == 500


async def test_get_condicao_unescapes_html_entities():
    """Deve decodificar entidades HTML nos valores dos hidden fields."""
    client = ICondominioClient()
    html = '<input type="hidden" name="Desc" value="SAL&Atilde;O DE FESTAS">'
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.url = "http://test/Reservas/Condicao"

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        available, fields = await client.get_condicao(
            httpx.Cookies(), date(2026, 6, 13), 2564, 9894
        )
        assert available is True
        assert fields["Desc"] == "SALÃO DE FESTAS"


async def test_get_condicao_skips_inputs_without_name():
    """Inputs sem atributo name devem ser ignorados."""
    client = ICondominioClient()
    html = """
    <input type="hidden" value="orphan">
    <input type="hidden" name="valid" value="ok">
    """
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.url = "http://test/Reservas/Condicao"

    with patch.object(client, "_ensure_client") as mock_ensure:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ensure.return_value = mock_http

        available, fields = await client.get_condicao(
            httpx.Cookies(), date(2026, 6, 13), 2564, 9894
        )
        assert available is True
        assert "valid" in fields
        assert len(fields) == 1


async def test_execute_reservation_handles_retry_exception(db, seed_resources):
    """Erros durante retry loop devem ser logados e continuar."""
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation, ["resource"])

    client = ICondominioClient()

    condicao_calls = [
        Exception("Network error"),
        (True, {"field": "value"}),
    ]

    with (
        patch.object(client, "login", return_value=("niu", "token")),
        patch.object(client, "redirect", return_value="https://auth-url"),
        patch.object(client, "authenticate", return_value=httpx.Cookies()),
        patch.object(client, "warmup"),
        patch.object(client, "get_condicao", side_effect=condicao_calls),
        patch.object(client, "submit", return_value=(True, "Sucesso")),
        patch("app.services.icondominio.asyncio.sleep"),
    ):
        success = await client.execute_reservation(db, reservation, reservation.resource)

    assert success is True
    assert reservation.attempt_count == 2


async def test_execute_reservation_submit_fails_then_succeeds(db, seed_resources):
    """Submit que falha deve continuar tentando."""
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation, ["resource"])

    client = ICondominioClient()

    submit_calls = [
        (False, "Error page"),
        (True, "Sucesso"),
    ]

    with (
        patch.object(client, "login", return_value=("niu", "token")),
        patch.object(client, "redirect", return_value="https://auth-url"),
        patch.object(client, "authenticate", return_value=httpx.Cookies()),
        patch.object(client, "warmup"),
        patch.object(client, "get_condicao", return_value=(True, {"f": "v"})),
        patch.object(client, "submit", side_effect=submit_calls),
        patch("app.services.icondominio.asyncio.sleep"),
    ):
        success = await client.execute_reservation(db, reservation, reservation.resource)

    assert success is True
