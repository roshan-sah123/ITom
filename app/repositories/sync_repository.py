"""Asynchronous repository for telemetry sync runs and error audit logs."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sync import SyncErrorLog, SyncRun
from app.repositories.base import BaseRepository


class SyncRepository(BaseRepository[SyncRun]):
    """Repository managing sync run audits and diagnostic error traces."""

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        super().__init__(SyncRun, session)

    async def get_latest_sync_run(
        self, source_system: Optional[str] = None
    ) -> Optional[SyncRun]:
        """Fetch the most recent completed or running telemetry synchronization."""
        if self.session is None:
            return None
        stmt = select(SyncRun).options(selectinload(SyncRun.error_logs))
        if source_system:
            stmt = stmt.where(SyncRun.source_system == source_system.upper())
        stmt = stmt.order_by(desc(SyncRun.started_at)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_sync_runs_paginated(
        self, page: int = 1, page_size: int = 25
    ) -> List[SyncRun]:
        """Fetch paginated sync runs with eager-loaded error logs."""
        if self.session is None:
            return []
        offset = max(0, (page - 1) * page_size)
        stmt = (
            select(SyncRun)
            .options(selectinload(SyncRun.error_logs))
            .order_by(desc(SyncRun.started_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def complete_sync_run(
        self,
        run_id: uuid.UUID | str,
        status: str = "SUCCESS",
        items_extracted: int = 0,
        items_persisted: int = 0,
        items_updated: int = 0,
        records_unchanged: int = 0,
        duration_ms: int = 0,
    ) -> Optional[SyncRun]:
        """Update and finalize a SyncRun record with summary metrics."""
        if self.session is None:
            return None
        target_id = uuid.UUID(str(run_id)) if isinstance(run_id, str) else run_id
        run = await self.get_by_id(target_id)
        if run:
            run.status = status
            run.items_extracted = items_extracted
            run.items_persisted = items_persisted
            run.records_updated = items_updated
            run.records_unchanged = records_unchanged
            run.records_processed = items_extracted
            run.duration_ms = duration_ms
            run.completed_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(run)
        return run

    async def log_error(
        self,
        sync_run_id: uuid.UUID | str,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[SyncErrorLog]:
        """Create and persist an error log associated with a SyncRun."""
        if self.session is None:
            return None
        target_id = uuid.UUID(str(sync_run_id)) if isinstance(sync_run_id, str) else sync_run_id
        error_log = SyncErrorLog(
            id=uuid.uuid4(),
            sync_run_id=target_id,
            error_code=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            context_data=context_data or {},
            occurred_at=datetime.now(timezone.utc),
        )
        self.session.add(error_log)
        await self.session.flush()
        await self.session.refresh(error_log)
        return error_log

    async def get_error_logs_by_run_id(
        self, sync_run_id: uuid.UUID | str
    ) -> List[SyncErrorLog]:
        """Fetch all error logs for a specific sync execution run."""
        if self.session is None:
            return []
        target_id = uuid.UUID(str(sync_run_id)) if isinstance(sync_run_id, str) else sync_run_id
        stmt = (
            select(SyncErrorLog)
            .where(SyncErrorLog.sync_run_id == target_id)
            .order_by(desc(SyncErrorLog.occurred_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
