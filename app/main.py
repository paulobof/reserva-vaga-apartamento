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
from app.models import SEED_RESOURCES, Base, Resource
from app.routers.reservations import router
from app.services.scheduler import scheduler, start_scheduler, stop_scheduler

setup_logging()
logger = logging.getLogger("icond")


async def init_db() -> None:
    """Cria tabelas e insere seed data de recursos se necessário."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        result = await db.execute(select(Resource))
        if not result.scalars().first():
            for r in SEED_RESOURCES:
                db.add(
                    Resource(
                        id=r.id,
                        name=r.name,
                        recurso_id=r.recurso_id,
                        periodo_id=r.periodo_id,
                        hash=r.hash,
                    )
                )
            await db.commit()
            logger.info("Seeded %d resources", len(SEED_RESOURCES))


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
