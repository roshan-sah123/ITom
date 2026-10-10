"""Preview/apply database mapping changes and backfill without upstream calls.

python scripts/manage_locations.py                  # preview bootstrap/backfill, rollback
python scripts/manage_locations.py --apply          # commit initial assignments
python scripts/manage_locations.py --rules rules.json --apply  # validated replacement
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import asyncio
import json
from app.core.database import AsyncSessionLocal, engine
from app.services.location_service import LocationService


async def run(args):
    async with AsyncSessionLocal() as session:
        service=LocationService(session)
        try:
            if args.rules:
                payload=json.loads(Path(args.rules).read_text(encoding='utf-8'))
                await service.install_rules(payload['rules'])
            result=await service.backfill()
            if args.apply:
                await session.commit()
            else:
                await session.rollback()
            print(json.dumps({'applied':args.apply,'assignments':result},indent=2))
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--rules',help='Validated JSON rule revision; no Excel dependency')
    asyncio.run(run(parser.parse_args()))
