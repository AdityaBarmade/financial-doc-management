"""
app/db/session.py — Database Session Management

Provides:
- Async SQLAlchemy engine & session factory
- Dependency injection function for FastAPI routes
- DB initialization (create tables)
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── SQLAlchemy Engine ────────────────────────────────────────────────────────
# SQLite needs different settings than PostgreSQL
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # SQLite: StaticPool for in-process sharing, check_same_thread=False for async
    from sqlalchemy.pool import StaticPool
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # PostgreSQL / other databases
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

# ─── Session Factory ──────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,        # Don't expire objects after commit
    autocommit=False,
    autoflush=False,
)


# ─── Base Model ───────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ─── DB Initialization ────────────────────────────────────────────────────────
async def init_db():
    """
    Create all tables defined in models if they don't exist.
    Import models here to ensure they're registered with Base.metadata.
    """
    # Late imports to avoid circular dependencies
    from app.models import user, document, role  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


# ─── FastAPI Dependency ───────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides an async DB session.

    Usage in routes:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
