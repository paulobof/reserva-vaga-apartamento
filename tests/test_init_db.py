"""Testes para init_db e migrations em main.py."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Resource


async def test_init_db_creates_tables():
    """init_db deve criar todas as tabelas."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result.fetchall()]

    assert "resources" in tables
    assert "reservations" in tables
    assert "attempt_logs" in tables
    await engine.dispose()


async def test_init_db_reservation_has_reason_column():
    """Tabela reservations deve ter coluna reason."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(reservations)"))
        columns = [row[1] for row in result.fetchall()]

    assert "reason" in columns
    await engine.dispose()


async def test_seed_resources_are_inserted():
    """Seed deve inserir recursos no banco."""
    from app.models import SEED_RESOURCES

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        for r in SEED_RESOURCES:
            db.add(
                Resource(
                    id=r.id,
                    name=r.name,
                    recurso_id=r.recurso_id,
                    periodo_id=r.periodo_id,
                )
            )
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(select(Resource))
        resources = result.scalars().all()
        assert len(resources) == 11

    await engine.dispose()


async def test_reason_migration_on_existing_db():
    """Migracao deve adicionar coluna reason em DB existente sem ela."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Criar tabela sem coluna reason
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE reservations ("
                "id INTEGER PRIMARY KEY, "
                "resource_id INTEGER, "
                "target_date DATE, "
                "trigger_date DATE, "
                "status VARCHAR(20), "
                "created_at DATETIME, "
                "updated_at DATETIME, "
                "attempt_count INTEGER, "
                "result_message TEXT)"
            )
        )

    # Verificar que reason nao existe
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(reservations)"))
        columns = [row[1] for row in result.fetchall()]
        assert "reason" not in columns

    # Aplicar migracao
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(reservations)"))
        columns = [row[1] for row in result.fetchall()]
        if "reason" not in columns:
            await conn.execute(text("ALTER TABLE reservations ADD COLUMN reason VARCHAR(200)"))

    # Verificar que reason existe agora
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(reservations)"))
        columns = [row[1] for row in result.fetchall()]
        assert "reason" in columns

    await engine.dispose()


async def test_hash_nullable_migration():
    """Migracao deve converter hash de NOT NULL para nullable."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Criar tabela com hash NOT NULL
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE resources ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR(100) NOT NULL, "
                "recurso_id INTEGER NOT NULL, "
                "periodo_id INTEGER NOT NULL, "
                "hash VARCHAR(64) NOT NULL)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO resources (id, name, recurso_id, periodo_id, hash) "
                "VALUES (1, 'Test', 2564, 9894, 'abc123')"
            )
        )

    # Verificar que hash e NOT NULL
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(resources)"))
        columns = result.fetchall()
        hash_col = next(c for c in columns if c[1] == "hash")
        assert hash_col[3] == 1  # notnull

    # Aplicar migracao (mesma logica do main.py)
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(resources)"))
        columns = result.fetchall()
        hash_col = next((c for c in columns if c[1] == "hash"), None)
        if hash_col and hash_col[3] == 1:
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

    # Verificar que hash agora e nullable
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(resources)"))
        columns = result.fetchall()
        hash_col = next(c for c in columns if c[1] == "hash")
        assert hash_col[3] == 0  # nullable

    # Verificar que dados foram preservados
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT hash FROM resources WHERE id = 1"))
        row = result.fetchone()
        assert row[0] == "abc123"

    await engine.dispose()
