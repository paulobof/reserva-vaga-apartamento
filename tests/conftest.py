"""Fixtures compartilhadas para todos os testes."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Reservation, Resource


@pytest.fixture
async def engine():
    """Engine SQLite in-memory para testes."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine):
    """Sessao de banco de dados para um teste individual."""
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seed_resources(db):
    """Seed de recursos no banco de teste."""
    resources = [
        Resource(id=1, name="Salao de Festas Adulto", recurso_id=2564, periodo_id=9894),
        Resource(id=2, name="Churrasqueira com Forno de Pizza", recurso_id=2563, periodo_id=9894),
    ]
    for r in resources:
        db.add(r)
    await db.commit()
    return resources


@pytest.fixture
async def sample_reservation(db, seed_resources):
    """Reserva de exemplo para testes."""
    reservation = Reservation(
        resource_id=1,
        target_date=date(2026, 6, 13),
        trigger_date=date(2026, 3, 14),
        status="scheduled",
        reason="Aniversario",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)
    return reservation


@pytest.fixture
async def app_client(engine):
    """HTTP client para testes de rotas (usa DB in-memory)."""
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed resources
    async with session_factory() as session:
        session.add(Resource(id=1, name="Salao de Festas Adulto", recurso_id=2564, periodo_id=9894))
        session.add(
            Resource(
                id=2, name="Churrasqueira com Forno de Pizza", recurso_id=2563, periodo_id=9894
            )
        )
        await session.commit()

    from app.database import get_db
    from app.main import app

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_run_reservation():
    """Mock do run_reservation para testes de router."""
    with patch("app.routers.reservations.run_reservation", new_callable=AsyncMock) as mock:
        yield mock
