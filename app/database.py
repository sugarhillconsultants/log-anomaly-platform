"""
app/database.py

Async SQLAlchemy 2.0 + aiosqlite for local/demo use. Swap DATABASE_URL
for asyncpg/PostgreSQL in production — same SQLAlchemy API either way.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./log_events.db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class LogEventRecord(Base):
    __tablename__ = "log_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String)
    predicted_label: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def event_id(self) -> int:
        """Bridges this table's 'id' primary key to the API response
        model's 'event_id' field name, so from_attributes-based
        serialization in main.py's LogEventOut can find it via getattr."""
        return self.id

    @property
    def event_id(self) -> int:
        """Bridges this table's 'id' primary key to the API response
        model's 'event_id' field name, so from_attributes-based
        serialization in main.py's LogEventOut can find it via getattr."""
        return self.id


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
