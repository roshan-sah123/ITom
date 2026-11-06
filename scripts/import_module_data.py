"""Copy a frozen module SQLite snapshot into an empty migrated PostgreSQL target.

Run only against a backup snapshot while module writes are stopped. The target
URL comes from DATABASE_URL_2; credentials are never accepted on the command line.
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import DateTime, func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.models.base import Base
from app.models.module_storage import MODULE_TABLE_NAMES


async def copy_module_data(source, destination, tables):
    """Copy in a transaction; never merge or overwrite an existing target."""
    if destination.dialect.name == 'postgresql':
        for table in tables:
            await destination.execute(text(f'LOCK TABLE "{table.name}" IN ACCESS EXCLUSIVE MODE'))
    for table in tables:
        if await destination.scalar(select(func.count()).select_from(table)):
            raise ValueError(f"Target table {table.name} is not empty")
    counts = {}
    for table in tables:
        result = await source.execute(select(table))
        rows = [dict(row) for row in result.mappings()]
        for row in rows:
            for column in table.columns:
                value = row[column.name]
                if isinstance(column.type, DateTime) and isinstance(value, datetime) and value.tzinfo is None:
                    row[column.name] = value.replace(tzinfo=timezone.utc)
        for offset in range(0, len(rows), 250):
            await destination.execute(table.insert(), rows[offset:offset + 250])
        counts[table.name] = len(rows)
        copied = [dict(row) for row in (await destination.execute(select(table))).mappings()]
        def normalize(row):
            return {key: value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value
                    for key, value in row.items()}
        key = lambda row: tuple(str(row[column.name]) for column in table.primary_key.columns)
        if sorted((normalize(row) for row in rows), key=key) != sorted((normalize(row) for row in copied), key=key):
            raise ValueError(f"Data verification failed for {table.name}")
    if destination.dialect.name == 'postgresql':
        for name in ('vendor_submissions', 'knowledge_content'):
            if name not in counts:
                continue
            sequence = await destination.scalar(text("SELECT pg_get_serial_sequence(:table_name, 'id')"), {'table_name': name})
            if not sequence:
                raise ValueError(f"Missing ID sequence for {name}")
            maximum = await destination.scalar(select(func.max(Base.metadata.tables[name].c.id)))
            await destination.execute(text('SELECT setval(CAST(:sequence AS regclass), :value, :called)'),
                                      {'sequence': sequence, 'value': maximum or 1, 'called': maximum is not None})
    return counts


async def run(snapshot):
    if not snapshot.is_file():
        raise ValueError('Source snapshot does not exist')
    if not settings.module_database_url.startswith('postgresql+asyncpg://'):
        raise ValueError('DATABASE_URL_2 must point to the PostgreSQL target')
    primary, module = make_url(settings.async_database_url), make_url(settings.module_database_url)
    if primary.get_backend_name() != 'postgresql' or (primary.host, primary.port or 5432, primary.database) != (module.host, module.port or 5432, module.database):
        raise ValueError('DATABASE_URL and DATABASE_URL_2 must point to the same PostgreSQL database')
    source = create_async_engine(URL.create('sqlite+aiosqlite', database='file:' + snapshot.as_posix(),
                                           query={'mode': 'ro', 'uri': 'true'}))
    target = create_async_engine(settings.module_database_url)
    try:
        async with source.connect() as src, target.begin() as dst:
            revisions = (await src.execute(text('SELECT version_num FROM module_alembic_version'))).scalars().all()
            target_revisions = (await dst.execute(text('SELECT version_num FROM module_alembic_version'))).scalars().all()
            if revisions != ['0001_module_storage'] or target_revisions != ['0001_module_storage']:
                raise ValueError('Source or target module schema revision is not supported')
            if (await dst.execute(text('SELECT version_num FROM alembic_version'))).scalars().all() != ['0013_knowledge_content']:
                raise ValueError('Target primary schema revision is not supported')
            tables = [Base.metadata.tables[name] for name in sorted(MODULE_TABLE_NAMES)]
            counts = await copy_module_data(src, dst, tables)
        for name, count in counts.items():
            print(f'{name}: {count}')
        print('Import committed. Verify records and attachments before cutover.')
    finally:
        await source.dispose()
        await target.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path, help='Path to the database-aware SQLite backup')
    args = parser.parse_args()
    asyncio.run(run(args.snapshot.resolve()))
