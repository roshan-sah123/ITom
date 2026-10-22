"""Run actual Alembic upgrades against a new database, independently of ORM bootstrap."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models.base import Base

ROOT = Path(__file__).resolve().parents[1]


def migrate(path, *arguments):
    environment = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{path.as_posix()}", SCHEDULER_ENABLED="false")
    return subprocess.run([sys.executable, "-m", "alembic", *arguments], cwd=ROOT, env=environment,
                          capture_output=True, text=True, timeout=30)


@pytest.fixture
def migrated_database(tmp_path):
    path = tmp_path / "migrated.db"
    result = migrate(path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    return path


def test_clean_upgrade_creates_model_columns_and_current_revision(migrated_database):
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    with sqlite3.connect(migrated_database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == ScriptDirectory.from_config(config).get_current_head()
        for table in Base.metadata.sorted_tables:
            columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table.name}")')}
            assert columns == set(table.columns.keys()), f"Migration/ORM columns differ for {table.name}"
    assert migrate(migrated_database, "upgrade", "head").returncode == 0


def test_group_migration_roundtrip_preserves_legacy_audits(migrated_database):
    path = migrated_database
    assert migrate(path, 'downgrade', '0007_location_review').returncode == 0
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO sync_runs (id,source_system,status,records_processed,records_updated,
            records_unchanged,items_extracted,items_persisted,duration_ms,started_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", ('b'*32,'SOLARWINDS','SUCCESS',1,0,0,1,1,1,'2026-10-01'))
        db.commit()
    assert migrate(path, 'upgrade', 'head').returncode == 0
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT groups_extracted,memberships_extracted FROM sync_runs').fetchall() == [(None,None)]
        assert db.execute('SELECT COUNT(*) FROM solarwinds_groups').fetchone()[0] == 0
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_group_migration_compiles_postgresql_upgrade_and_downgrade():
    import importlib.util
    from io import StringIO
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec = importlib.util.spec_from_file_location('group_migration', ROOT/'alembic/versions/0008_solarwinds_groups.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    output = StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
    with Operations.context(context):
        module.upgrade(); module.downgrade()
    sql = output.getvalue()
    assert 'CREATE TABLE solarwinds_groups' in sql
    assert 'ci_id UUID' in sql and 'member_id BIGINT' in sql
    assert 'DROP TABLE solarwinds_group_members' in sql


def test_group_links_sqlite_roundtrip_and_postgresql_ddl(migrated_database):
    assert migrate(migrated_database,'downgrade','0008_solarwinds_groups').returncode==0
    with sqlite3.connect(migrated_database) as db:
        db.execute("INSERT INTO solarwinds_groups VALUES (10,'Exact  (Kraków)',1,'Up')")
        db.commit()
    assert migrate(migrated_database,'upgrade','head').returncode==0
    with sqlite3.connect(migrated_database) as db:
        assert db.execute('SELECT name,is_active FROM solarwinds_groups').fetchone()==('Exact  (Kraków)',1)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    import importlib.util
    from io import StringIO
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec=importlib.util.spec_from_file_location('links_migration',ROOT/'alembic/versions/0009_group_site_scores.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=StringIO()
    context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
    with Operations.context(context): module.upgrade();module.downgrade()
    assert 'CREATE TABLE solarwinds_group_locations' in output.getvalue()
    assert 'ALTER TABLE solarwinds_groups DROP COLUMN is_active' in output.getvalue()


def test_location_review_upgrade_preserves_legacy_targets_and_no_fabricated_reviewers(tmp_path):
    path=tmp_path/'legacy-locations.db'
    assert migrate(path,'upgrade','0006_canonical_locations').returncode==0
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO locations(id,name,level,created_at,updated_at) VALUES ('site','Legacy site','city','2026-10-01','2026-10-01')")
        for key,target,note in [('known','site','Verified source spelling'),('review','site','City conflict requires review'),('empty',None,None)]:
            db.execute('INSERT INTO location_mapping_rules(id,source_system,match_key,location_id,revision,enabled,review_note) VALUES (?,?,?,?,?,?,?)',
                       (key,'INTUNE',key,target,'legacy',1,note))
        db.execute("""INSERT INTO configuration_items(id,source_id,source_system,name,ci_type,status,health_tier,vendor,attributes,
            last_sync_time,created_at,updated_at,location_id,location_rule_id,location_resolution)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",('a'*32,'legacy-device','INTUNE','known-001','Windows','Compliant','High','Dell','{}',
            '2026-10-01','2026-10-01','2026-10-01','site','known','mapped'))
        db.commit()
    result=migrate(path,'upgrade','head')
    assert result.returncode==0,result.stderr
    with sqlite3.connect(path) as db:
        rows={r[0]:r[1:] for r in db.execute('SELECT id,approval_status,reviewed_by,reviewed_at FROM location_mapping_rules')}
        assert rows=={'known':('APPROVED',None,None),'review':('PENDING',None,None),'empty':('PENDING',None,None)}
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT location_rule_id FROM configuration_items').fetchone()[0]=='known'
    assert migrate(path,'downgrade','0006_canonical_locations').returncode==0
    assert migrate(path,'upgrade','head').returncode==0


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Audit P2: revision 0004 has a no-op upgrade and omits three ORM indexes")
def test_clean_upgrade_creates_all_model_indexes(migrated_database):
    with sqlite3.connect(migrated_database) as db:
        indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    required = {index.name for table in Base.metadata.tables.values() for index in table.indexes}
    assert required <= indexes, f"Missing migration indexes: {sorted(required - indexes)}"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Audit P2: revision 0004 downgrade drops indexes that its upgrade never created")
def test_fresh_database_can_downgrade_and_upgrade(migrated_database):
    result = migrate(migrated_database, "downgrade", "base")
    assert result.returncode == 0, result.stderr
    assert migrate(migrated_database, "upgrade", "head").returncode == 0
