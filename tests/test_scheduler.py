"""Testes para services/scheduler.py - Scheduling logic e cron jobs."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scheduler import (
    _run_reservation_at_midnight,
    compute_trigger_date,
    is_within_window,
    nightly_check,
    opens_tonight,
    run_reservation,
    start_scheduler,
    stop_scheduler,
)

# ===== Testes de funcoes puras (date logic) =====


def test_compute_trigger_date():
    target = date(2026, 6, 13)
    assert compute_trigger_date(target) == target - timedelta(days=91)


def test_compute_trigger_date_near():
    target = date.today() + timedelta(days=91)
    assert compute_trigger_date(target) == date.today()


def test_is_within_window_true():
    target = date.today() + timedelta(days=30)
    assert is_within_window(target) is True


def test_is_within_window_true_at_1_day():
    target = date.today() + timedelta(days=1)
    assert is_within_window(target) is True


def test_is_within_window_true_at_89_days():
    target = date.today() + timedelta(days=89)
    assert is_within_window(target) is True


def test_is_within_window_false_at_90():
    """delta == 90 means window opens tonight, NOT within window yet."""
    target = date.today() + timedelta(days=90)
    assert is_within_window(target) is False


def test_is_within_window_false_past():
    target = date.today() - timedelta(days=1)
    assert is_within_window(target) is False


def test_is_within_window_false_today():
    target = date.today()
    assert is_within_window(target) is False


def test_is_within_window_false_too_far():
    target = date.today() + timedelta(days=100)
    assert is_within_window(target) is False


def test_opens_tonight_true():
    target = date.today() + timedelta(days=90)
    assert opens_tonight(target) is True


def test_opens_tonight_false():
    target = date.today() + timedelta(days=89)
    assert opens_tonight(target) is False


def test_opens_tonight_false_91():
    target = date.today() + timedelta(days=91)
    assert opens_tonight(target) is False


# ===== Testes para nightly_check =====


async def test_nightly_check_no_reservations():
    """Nao deve criar tasks quando nao ha reservas para disparar."""
    with patch("app.services.scheduler.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        await nightly_check()


async def test_nightly_check_with_reservations():
    """Deve criar tasks para cada reserva encontrada."""
    mock_reservation = MagicMock()
    mock_reservation.id = 1
    mock_reservation.resource_id = 2564
    mock_reservation.resource.name = "Salao"
    mock_reservation.target_date = date(2026, 6, 13)

    with (
        patch("app.services.scheduler.async_session") as mock_session_factory,
        patch("app.services.scheduler.asyncio.create_task") as mock_create_task,
    ):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_reservation]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        await nightly_check()
        mock_create_task.assert_called_once()


# ===== Testes para _run_reservation_at_midnight =====


async def test_run_reservation_at_midnight_waits_and_runs():
    """Deve esperar ate 23:59:30 e entao chamar run_reservation."""
    with (
        patch("app.services.scheduler.datetime") as mock_dt,
        patch("app.services.scheduler.asyncio.sleep") as mock_sleep,
        patch("app.services.scheduler.run_reservation") as mock_run,
    ):
        # Simular horario 23:00:00
        mock_now = MagicMock()
        mock_now.replace.return_value = MagicMock()
        mock_now.replace.return_value.__sub__ = MagicMock(
            return_value=MagicMock(total_seconds=MagicMock(return_value=3570.0))
        )
        mock_dt.now.return_value = mock_now

        mock_run.return_value = None

        await _run_reservation_at_midnight(1, 2564)
        mock_sleep.assert_called_once_with(3570.0)
        mock_run.assert_called_once_with(1)


async def test_run_reservation_at_midnight_no_wait_if_past():
    """Se ja passou de 23:59:30, executa imediatamente."""
    with (
        patch("app.services.scheduler.datetime") as mock_dt,
        patch("app.services.scheduler.asyncio.sleep") as mock_sleep,
        patch("app.services.scheduler.run_reservation") as mock_run,
    ):
        mock_now = MagicMock()
        mock_now.replace.return_value = MagicMock()
        mock_now.replace.return_value.__sub__ = MagicMock(
            return_value=MagicMock(total_seconds=MagicMock(return_value=-30.0))
        )
        mock_dt.now.return_value = mock_now
        mock_run.return_value = None

        await _run_reservation_at_midnight(1, 2564)
        mock_sleep.assert_not_called()
        mock_run.assert_called_once_with(1)


# ===== Testes para run_reservation =====


async def test_run_reservation_success():
    """Fluxo completo com sucesso deve enviar WhatsApp."""
    mock_reservation = MagicMock()
    mock_reservation.id = 1
    mock_reservation.resource.name = "Salao"
    mock_reservation.target_date = date(2026, 6, 13)
    mock_reservation.status = "success"
    mock_reservation.attempt_count = 1
    mock_reservation.result_message = None
    mock_reservation.reason = "Aniversario"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_reservation

    with (
        patch("app.services.scheduler.async_session") as mock_session_factory,
        patch("app.services.scheduler.ICondominioClient") as mock_client_class,
        patch("app.services.scheduler.send_whatsapp") as mock_whatsapp,
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        mock_client = AsyncMock()
        mock_client.execute_reservation = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        await run_reservation(1)

        mock_client.execute_reservation.assert_called_once()
        mock_whatsapp.assert_called_once()
        # Verifica que o motivo esta na mensagem
        call_args = mock_whatsapp.call_args[0][0]
        assert "Aniversario" in call_args
        mock_client.close.assert_called_once()


async def test_run_reservation_failure():
    """Falha deve enviar WhatsApp com status de erro."""
    mock_reservation = MagicMock()
    mock_reservation.id = 2
    mock_reservation.resource.name = "Churrasqueira"
    mock_reservation.target_date = date(2026, 6, 13)
    mock_reservation.status = "failed"
    mock_reservation.attempt_count = 60
    mock_reservation.result_message = "Falhou apos 60 tentativas"
    mock_reservation.reason = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_reservation

    with (
        patch("app.services.scheduler.async_session") as mock_session_factory,
        patch("app.services.scheduler.ICondominioClient") as mock_client_class,
        patch("app.services.scheduler.send_whatsapp") as mock_whatsapp,
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        mock_client = AsyncMock()
        mock_client.execute_reservation = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        await run_reservation(2)
        mock_whatsapp.assert_called_once()
        call_args = mock_whatsapp.call_args[0][0]
        assert "Motivo" not in call_args  # reason is None


async def test_run_reservation_not_found():
    """Reserva inexistente deve retornar sem erro."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    with (
        patch("app.services.scheduler.async_session") as mock_session_factory,
        patch("app.services.scheduler.ICondominioClient") as mock_client_class,
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        await run_reservation(999)
        mock_client.execute_reservation.assert_not_called()
        mock_client.close.assert_called_once()


# ===== Testes para start/stop scheduler =====


def test_start_scheduler():
    with patch("app.services.scheduler.scheduler") as mock_scheduler:
        start_scheduler()
        mock_scheduler.add_job.assert_called_once()
        mock_scheduler.start.assert_called_once()


def test_stop_scheduler_when_running():
    with patch("app.services.scheduler.scheduler") as mock_scheduler:
        mock_scheduler.running = True
        stop_scheduler()
        mock_scheduler.shutdown.assert_called_once_with(wait=False)


def test_stop_scheduler_when_not_running():
    with patch("app.services.scheduler.scheduler") as mock_scheduler:
        mock_scheduler.running = False
        stop_scheduler()
        mock_scheduler.shutdown.assert_not_called()
