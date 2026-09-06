"""Generic asynchronous CRUD repository pattern using SQLAlchemy 2.0 AsyncSession."""

import uuid
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository providing standard async CRUD operations."""

    def __init__(self, model: Type[ModelType], session: Optional[AsyncSession] = None) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: uuid.UUID | str) -> Optional[ModelType]:
        """Fetch a single record by primary key."""
        if self.session is None:
            return None
        target_id = uuid.UUID(str(id)) if isinstance(id, str) else id
        statement = select(self.model).where(self.model.id == target_id)
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Fetch multiple records with pagination."""
        if self.session is None:
            return []
        statement = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count total records in the model table."""
        if self.session is None:
            return 0
        statement = select(func.count()).select_from(self.model)
        result = await self.session.execute(statement)
        return result.scalar_one() or 0

    async def create(self, db_obj: ModelType) -> ModelType:
        """Add and persist a new model instance."""
        if self.session is not None:
            self.session.add(db_obj)
            await self.session.flush()
            await self.session.refresh(db_obj)
        return db_obj

    async def delete(self, id: uuid.UUID | str) -> bool:
        """Delete a record by primary key."""
        if self.session is None:
            return False
        target_id = uuid.UUID(str(id)) if isinstance(id, str) else id
        statement = delete(self.model).where(self.model.id == target_id)
        result = await self.session.execute(statement)
        await self.session.flush()
        return result.rowcount > 0
