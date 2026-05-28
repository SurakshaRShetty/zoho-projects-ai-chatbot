"""
Long-term memory CRUD on top of the LongTermMemory SQLAlchemy model.
Each user's memories are key-value pairs persisted across sessions.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.db import LongTermMemory


async def get_memory(db: AsyncSession, user_id: int, key: str) -> str | None:
    result = await db.execute(
        select(LongTermMemory).where(
            LongTermMemory.user_id == user_id,
            LongTermMemory.key == key,
        )
    )
    row = result.scalar_one_or_none()
    return row.value if row else None


async def set_memory(db: AsyncSession, user_id: int, key: str, value: str) -> None:
    result = await db.execute(
        select(LongTermMemory).where(
            LongTermMemory.user_id == user_id,
            LongTermMemory.key == key,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(LongTermMemory(user_id=user_id, key=key, value=value))
    await db.commit()


async def get_all_memories(db: AsyncSession, user_id: int) -> dict[str, str]:
    result = await db.execute(
        select(LongTermMemory).where(LongTermMemory.user_id == user_id)
    )
    return {row.key: row.value for row in result.scalars().all()}


async def delete_memory(db: AsyncSession, user_id: int, key: str) -> None:
    result = await db.execute(
        select(LongTermMemory).where(
            LongTermMemory.user_id == user_id,
            LongTermMemory.key == key,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
