from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

# ── Engine ────────────────────────────────────────────────────
# echo=True prints all SQL to console in dev — helpful for debugging
engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
    future=True,
)

# ── Session factory ───────────────────────────────────────────
# expire_on_commit=False keeps ORM objects accessible after commit
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base class for all ORM models ─────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an AsyncSession per request.
    The 'async with' guarantees the session is closed even if an exception occurs.
    Usage in routes:  db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        yield session


# ── Create all tables ─────────────────────────────────────────
async def init_db() -> None:
    """
    Creates all tables defined in ORM models.
    Called once at app startup. Safe to call repeatedly (uses CREATE IF NOT EXISTS).
    """
    async with engine.begin() as conn:
        from backend.models import db as _  # noqa: F401 — import triggers model registration
        await conn.run_sync(Base.metadata.create_all)
