"""Start an isolated portal with deterministic inventory on an ephemeral port."""
import socket
import threading
import time

import pytest
import pytest_asyncio
import uvicorn
from datetime import datetime, timezone, timedelta
from app.models.location import Location

from tests.factories import make_ci, make_run


@pytest_asyncio.fixture
async def operator_inventory(session):
    session.add_all([Location(id='pune',name='Pune',level='city'),Location(id='noida',name='Noida',level='city')])
    await session.flush()
    now=datetime.now(timezone.utc)
    session.add_all([
        make_ci("SOLARWINDS", "HEALTHY-SERVER", "Up", "High", location="Pune",location_id='pune',location_resolution='mapped',attributes={'node_category':'Server','node_type':'Windows Server'}),
        make_ci("SOLARWINDS", "CRITICAL-SERVER", "Critical", "Low", location="Pune",location_id='pune',location_resolution='mapped',attributes={'node_category':'Server','node_type':'Linux Server'}),
        make_ci("SOLARWINDS", "DOWN-SWITCH", "Down", "Low", ci_type="Switch", vendor="Cisco", location="Noida",location_id='noida',location_resolution='mapped',attributes={'node_category':'Network','node_type':'Access Switch'}),
        make_ci("INTUNE", "COMPLIANT-LAPTOP", "Compliant", "High", ci_type="Windows",location_id='pune',location_resolution='mapped',attributes={'last_sync_date_time':now.isoformat()}),
        make_ci("INTUNE", "NONCOMPLIANT-LAPTOP", "NonCompliant", "Low", ci_type="Windows",location_id='pune',location_resolution='mapped',attributes={'last_sync_date_time':(now-timedelta(days=10)).isoformat()}),
        make_ci("INTUNE", "UNASSIGNED-LAPTOP", "Unknown", "Medium", ci_type="Windows", location_resolution='unassigned', attributes={}),
        make_run("SOLARWINDS"), make_run("INTUNE"),
    ])
    await session.commit()


@pytest_asyncio.fixture
async def catalogue_inventory(operator_inventory, session):
    now = datetime.now(timezone.utc)
    for index in range(27):
        location_id = f'office-{index}'
        session.add(Location(id=location_id, name=f'Office {index:02}', level='office'))
        await session.flush()
        session.add(make_ci('INTUNE', f'OFFICE-{index}-LAPTOP', 'Compliant', 'High',
                            location_id=location_id, location_resolution='mapped',
                            attributes={'last_sync_date_time': now.isoformat()}))
    await session.commit()


@pytest.fixture
def portal_url(api_environment, operator_inventory):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api_environment, host="127.0.0.1", port=port, log_level="warning"))
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Isolated portal failed to start"
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()
