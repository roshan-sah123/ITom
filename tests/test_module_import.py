import os
import uuid
import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.base import Base
from scripts.import_module_data import copy_module_data


@pytest.mark.asyncio
async def test_import_preserves_module_data_and_rejects_nonempty_destination(tmp_path):
    source = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source.db'}")
    destination = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")
    table = Base.metadata.tables['vendor_submissions']
    try:
        for engine in (source, destination):
            async with engine.begin() as conn:
                await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[table]))
        async with source.begin() as conn:
            await conn.execute(insert(table).values(id=42, request_id='request', payload_hash='a', vendor='Test', method='test', step_count=0, document={'steps': []}, revision=1, is_deleted=False))
        async with source.connect() as src, destination.begin() as dst:
            assert await copy_module_data(src, dst, [table]) == {'vendor_submissions': 1}
        async with destination.connect() as conn:
            row = (await conn.execute(select(table))).mappings().one()
            assert row['id'] == 42 and row['document'] == {'steps': []}
        async with source.connect() as src, destination.begin() as dst:
            with pytest.raises(ValueError, match='not empty'):
                await copy_module_data(src, dst, [table])
    finally:
        await source.dispose()
        await destination.dispose()


@pytest.mark.asyncio
async def test_postgres_import_and_next_generated_id(tmp_path):
    url = os.environ.get('ITOM_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Set ITOM_TEST_POSTGRES_URL to an isolated PostgreSQL test database')
    if not url.startswith('postgresql+asyncpg://'):
        pytest.fail('ITOM_TEST_POSTGRES_URL must use postgresql+asyncpg')
    schema = 'itom_import_test_' + uuid.uuid4().hex
    source = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source.db'}")
    target = create_async_engine(url)
    table = Base.metadata.tables['vendor_submissions']
    try:
        async with source.begin() as conn:
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[table]))
            await conn.execute(insert(table).values(id=42, request_id='one', payload_hash='a', vendor='Test', method='test', step_count=0, document={'steps': []}, revision=1, is_deleted=False))
        async with target.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[table]))
            async with source.connect() as src:
                await copy_module_data(src, conn, [table])
            result = await conn.execute(insert(table).values(request_id='two', payload_hash='b', vendor='Test', method='test', step_count=0, document={}, revision=1, is_deleted=False).returning(table.c.id))
            assert result.scalar_one() == 43
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        await source.dispose()
        await target.dispose()
