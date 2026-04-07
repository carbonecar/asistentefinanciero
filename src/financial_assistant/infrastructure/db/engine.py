from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(dsn, echo=False, pool_pre_ping=True, pool_size=5, max_overflow=10)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
