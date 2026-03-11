"""iCond - Reserva Automática iCondomínio. Ponto de entrada da aplicação."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text

from app.config import settings
from app.database import async_session, engine
from app.logging_config import setup_logging
from app.middleware import ObservabilityMiddleware
from app.models import SEED_PERIODS, SEED_RESOURCES, Base, Period, Resource
from app.routers.reservations import router
from app.services.scheduler import scheduler, start_scheduler, stop_scheduler

setup_logging()
logger = logging.getLogger("icond")


async def _migrate_hash_nullable(conn) -> None:
    """Migra coluna hash de NOT NULL para nullable (SQLite não suporta ALTER COLUMN)."""
    result = await conn.execute(text("PRAGMA table_info(resources)"))
    columns = result.fetchall()
    hash_col = next((c for c in columns if c[1] == "hash"), None)
    if hash_col and hash_col[3] == 1:  # notnull=1 → precisa migrar
        await conn.execute(
            text(
                "CREATE TABLE resources_new ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR(100) NOT NULL, "
                "recurso_id INTEGER NOT NULL, "
                "periodo_id INTEGER NOT NULL, "
                "hash VARCHAR(64))"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO resources_new "
                "SELECT id, name, recurso_id, periodo_id, hash FROM resources"
            )
        )
        await conn.execute(text("DROP TABLE resources"))
        await conn.execute(text("ALTER TABLE resources_new RENAME TO resources"))
        logger.info("Migrated resources.hash to nullable")


async def init_db() -> None:
    """Cria tabelas, aplica migrações e insere seed data de recursos."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrar hash para nullable se DB já existia com schema antigo
        tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        if "resources" in [t[0] for t in tables.fetchall()]:
            await _migrate_hash_nullable(conn)

    # Migrar: adicionar coluna reason em reservations se não existir
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(reservations)"))
        columns = [c[1] for c in result.fetchall()]
        if (
            "reservations"
            in [
                t[0]
                for t in (
                    await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                ).fetchall()
            ]
            and "reason" not in columns
        ):
            await conn.execute(text("ALTER TABLE reservations ADD COLUMN reason VARCHAR(200)"))
            logger.info("Migrated reservations: added reason column")

    # Migrar: adicionar coluna periodo_id em reservations se não existir
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(reservations)"))
        columns = [c[1] for c in result.fetchall()]
        if (
            "reservations"
            in [
                t[0]
                for t in (
                    await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                ).fetchall()
            ]
            and "periodo_id" not in columns
        ):
            await conn.execute(text("ALTER TABLE reservations ADD COLUMN periodo_id INTEGER"))
            logger.info("Migrated reservations: added periodo_id column")

    async with async_session() as db:
        existing = (await db.execute(select(Resource.id))).scalars().all()
        existing_ids = set(existing)
        added = 0
        for r in SEED_RESOURCES:
            if r.id not in existing_ids:
                db.add(
                    Resource(
                        id=r.id,
                        name=r.name,
                        recurso_id=r.recurso_id,
                        periodo_id=r.periodo_id,
                    )
                )
                added += 1
        if added:
            await db.commit()
            logger.info("Seeded %d new resources (total: %d)", added, len(SEED_RESOURCES))

        # Seed periods
        existing_periods = (await db.execute(select(Period.resource_id, Period.periodo_id))).all()
        existing_period_set = {(r, p) for r, p in existing_periods}
        added_periods = 0
        for p in SEED_PERIODS:
            if (p.resource_id, p.periodo_id) not in existing_period_set:
                db.add(
                    Period(
                        resource_id=p.resource_id,
                        periodo_id=p.periodo_id,
                        label=p.label,
                    )
                )
                added_periods += 1
        if added_periods:
            await db.commit()
            logger.info("Seeded %d new periods", added_periods)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia startup e shutdown da aplicação."""
    await init_db()
    start_scheduler()
    logger.info(
        "iCond started (version=%s, log_level=%s, log_format=%s)",
        settings.app_version,
        settings.log_level,
        settings.log_format,
    )
    yield
    stop_scheduler()
    await engine.dispose()
    logger.info("iCond stopped")


app = FastAPI(title="iCond - Reservas", version=settings.app_version, lifespan=lifespan)
app.add_middleware(ObservabilityMiddleware)
app.include_router(router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Retorna 204 para evitar 404 em requests automáticos do browser."""
    return Response(status_code=204)


@app.get("/security.txt", include_in_schema=False)
@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt() -> Response:
    """Retorna 204 para evitar 404 em requests de scanners."""
    return Response(status_code=204)


@app.get("/health")
async def health_check() -> JSONResponse:
    """Endpoint de health check para monitoramento (Dokploy/reverse proxy).

    Returns:
        JSON com status da aplicação, banco de dados e scheduler.
    """
    db_ok = False
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        logger.warning("Health check: database unreachable")

    scheduler_ok = scheduler.running

    status = "healthy" if (db_ok and scheduler_ok) else "degraded"
    status_code = 200 if status == "healthy" else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "version": settings.app_version,
            "checks": {
                "database": "ok" if db_ok else "error",
                "scheduler": "ok" if scheduler_ok else "error",
            },
        },
    )
