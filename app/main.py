import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.database import engine, async_session
from app.models import Base, Resource, SEED_RESOURCES
from app.routers.reservations import router
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("icond")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        result = await db.execute(select(Resource))
        if not result.scalars().first():
            for r in SEED_RESOURCES:
                db.add(Resource(
                    id=r.id, name=r.name, recurso_id=r.recurso_id,
                    periodo_id=r.periodo_id, hash=r.hash,
                ))
            await db.commit()
            logger.info("Seeded %d resources", len(SEED_RESOURCES))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    logger.info("iCond app started")
    yield
    stop_scheduler()
    await engine.dispose()
    logger.info("iCond app stopped")


app = FastAPI(title="iCond - Reservas", lifespan=lifespan)
app.include_router(router)
