"""Testes para models.py - ORM models e seed data."""

from datetime import date, datetime

from sqlalchemy import select

from app.models import SEED_RESOURCES, AttemptLog, Reservation, Resource


def test_seed_resources_has_11_items():
    assert len(SEED_RESOURCES) == 11


def test_seed_resources_all_have_required_fields():
    for r in SEED_RESOURCES:
        assert r.id is not None
        assert r.name
        assert r.recurso_id > 0
        assert r.periodo_id == 9894


def test_seed_resources_unique_ids():
    ids = [r.id for r in SEED_RESOURCES]
    assert len(ids) == len(set(ids))


def test_seed_resources_unique_recurso_ids():
    recurso_ids = [r.recurso_id for r in SEED_RESOURCES]
    assert len(recurso_ids) == len(set(recurso_ids))


async def test_resource_model_crud(db):
    resource = Resource(id=99, name="Test Resource", recurso_id=9999, periodo_id=9894)
    db.add(resource)
    await db.commit()

    result = await db.execute(select(Resource).where(Resource.id == 99))
    fetched = result.scalar_one()
    assert fetched.name == "Test Resource"
    assert fetched.recurso_id == 9999


async def test_reservation_model_crud(db, seed_resources):
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="pending",
        reason="Teste",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)

    assert reservation.id is not None
    assert reservation.status == "pending"
    assert reservation.reason == "Teste"
    assert reservation.attempt_count == 0
    assert reservation.created_at is not None


async def test_reservation_model_defaults(db, seed_resources):
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)

    assert reservation.status == "pending"
    assert reservation.attempt_count == 0
    assert reservation.reason is None
    assert reservation.result_message is None


async def test_reservation_resource_relationship(db, seed_resources):
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
    )
    db.add(reservation)
    await db.commit()

    result = await db.execute(select(Reservation).where(Reservation.id == reservation.id))
    fetched = result.scalar_one()
    await db.refresh(fetched, ["resource"])
    assert fetched.resource.name == "Salao de Festas Adulto"


async def test_attempt_log_model_crud(db, sample_reservation):
    log = AttemptLog(
        reservation_id=sample_reservation.id,
        attempt_number=1,
        timestamp=datetime.now(),
        step="auth",
        success=True,
        response_snippet="OK",
    )
    db.add(log)
    await db.commit()

    result = await db.execute(
        select(AttemptLog).where(AttemptLog.reservation_id == sample_reservation.id)
    )
    fetched = result.scalar_one()
    assert fetched.step == "auth"
    assert fetched.success is True


async def test_attempt_log_error_message(db, sample_reservation):
    log = AttemptLog(
        reservation_id=sample_reservation.id,
        attempt_number=1,
        timestamp=datetime.now(),
        step="condicao",
        success=False,
        error_message="Data nao disponivel",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    assert log.error_message == "Data nao disponivel"
    assert log.response_snippet is None
