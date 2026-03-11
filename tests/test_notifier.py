"""Testes para services/notifier.py - WhatsApp notification."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture
def _mock_api_key():
    """Garante que a API key esta configurada para testes."""
    with patch("app.services.notifier.settings") as mock_settings:
        mock_settings.evolution_api_key = "test-key"
        mock_settings.whatsapp_number = "5511999999999"
        yield mock_settings


@pytest.fixture
def _mock_no_api_key():
    """Simula API key nao configurada."""
    with patch("app.services.notifier.settings") as mock_settings:
        mock_settings.evolution_api_key = ""
        yield mock_settings


async def test_send_whatsapp_skips_without_api_key(_mock_no_api_key):
    from app.services.notifier import send_whatsapp

    # Nao deve levantar excecao
    await send_whatsapp("Test message")


async def test_send_whatsapp_sends_message(_mock_api_key):
    from app.services.notifier import send_whatsapp

    mock_response = httpx.Response(200, json={"status": "ok"})

    with patch("app.services.notifier.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        await send_whatsapp("Reserva confirmada!")

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["json"]["text"] == "Reserva confirmada!"
        assert call_kwargs[1]["json"]["number"] == "5511999999999"
        assert call_kwargs[1]["headers"]["apikey"] == "test-key"


async def test_send_whatsapp_handles_timeout(_mock_api_key):
    from app.services.notifier import send_whatsapp

    with patch("app.services.notifier.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        # Nao deve propagar excecao
        await send_whatsapp("Test message")


async def test_send_whatsapp_handles_http_error(_mock_api_key):
    from app.services.notifier import send_whatsapp

    mock_response = httpx.Response(500, text="Internal Server Error")
    mock_response._request = httpx.Request("POST", "http://test")

    with patch("app.services.notifier.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        # raise_for_status vai levantar HTTPStatusError, que cai no except generico
        await send_whatsapp("Test message")
