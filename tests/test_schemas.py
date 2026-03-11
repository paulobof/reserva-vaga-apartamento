"""Testes para schemas.py - Pydantic DTOs."""

from datetime import date, datetime

from app.schemas import AttemptLogOut, ReservationCreate, ReservationOut, ResourceOut


def test_resource_out_with_hash():
    data = ResourceOut(id=1, name="Salao", recurso_id=2564, periodo_id=9894, hash="abc123")
    assert data.hash == "abc123"


def test_resource_out_without_hash():
    data = ResourceOut(id=1, name="Salao", recurso_id=2564, periodo_id=9894)
    assert data.hash is None


def test_resource_out_hash_none():
    data = ResourceOut(id=1, name="Salao", recurso_id=2564, periodo_id=9894, hash=None)
    assert data.hash is None


def test_reservation_create_basic():
    data = ReservationCreate(resource_id=1, target_date=date(2026, 6, 13))
    assert data.resource_id == 1
    assert data.target_date == date(2026, 6, 13)
    assert data.reason == ""


def test_reservation_create_with_reason():
    data = ReservationCreate(resource_id=1, target_date=date(2026, 6, 13), reason="Aniversario")
    assert data.reason == "Aniversario"


def test_attempt_log_out():
    data = AttemptLogOut(
        id=1,
        attempt_number=1,
        timestamp=datetime(2026, 3, 14, 23, 59, 30),
        step="condicao",
        success=True,
        response_snippet="OK",
        error_message=None,
    )
    assert data.step == "condicao"
    assert data.success is True


def test_attempt_log_out_with_error():
    data = AttemptLogOut(
        id=1,
        attempt_number=1,
        timestamp=datetime.now(),
        step="auth",
        success=False,
        response_snippet=None,
        error_message="Login failed",
    )
    assert data.success is False
    assert data.error_message == "Login failed"


def test_reservation_out_basic():
    data = ReservationOut(
        id=1,
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        attempt_count=0,
    )
    assert data.reason is None
    assert data.result_message is None
    assert data.resource is None
    assert data.attempt_logs == []


def test_reservation_out_with_reason():
    data = ReservationOut(
        id=1,
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="scheduled",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        attempt_count=0,
        reason="Festa de aniversario",
    )
    assert data.reason == "Festa de aniversario"


def test_reservation_out_with_resource():
    resource = ResourceOut(id=1, name="Salao", recurso_id=2564, periodo_id=9894)
    data = ReservationOut(
        id=1,
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="success",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        attempt_count=5,
        resource=resource,
    )
    assert data.resource.name == "Salao"


def test_reservation_out_with_logs():
    log = AttemptLogOut(
        id=1,
        attempt_number=1,
        timestamp=datetime.now(),
        step="auth",
        success=True,
        response_snippet=None,
        error_message=None,
    )
    data = ReservationOut(
        id=1,
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="success",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        attempt_count=1,
        attempt_logs=[log],
    )
    assert len(data.attempt_logs) == 1
    assert data.attempt_logs[0].step == "auth"
