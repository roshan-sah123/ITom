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
            if args.group_link is not None or args.revoke_group_link is not None:
                from app.services.group_location_service import GroupLocationService
                links = GroupLocationService(session)
                if args.group_link is not None:
                    if not args.location_id:
                        raise ValueError('--location-id is required for a group link')
                    result = await links.approve(args.group_link, args.location_id, args.reviewer or '', args.comment or '')
                else:
                    result = await links.revoke(args.revoke_group_link, args.reviewer or '', args.comment or '')
            else:
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
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--rules',help='Validated JSON rule revision; no Excel dependency')
    action.add_argument('--group-link', type=int, help='Approve an explicit active top-level SolarWinds group ID')
    action.add_argument('--revoke-group-link', type=int, help='Revoke a previously approved group link')
    parser.add_argument('--location-id', help='Existing canonical/Intune location ID')
    parser.add_argument('--reviewer', help='Named operator responsible for the decision')
    parser.add_argument('--comment', help='Evidence establishing the location correspondence')
    asyncio.run(run(parser.parse_args()))
