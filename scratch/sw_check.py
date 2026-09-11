import os
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from src.sync.solarwinds_client import SolarWindsClient

sw = SolarWindsClient(timeout=15)
q = """
SELECT TOP 5
    n.NodeID,
    n.Caption,
    n.Status,
    n.CPULoad,
    n.PercentMemoryUsed,
    cp.City,
    cp.ITSM_Location
FROM Orion.Nodes n
LEFT JOIN Orion.NodesCustomProperties cp ON n.NodeID = cp.NodeID
"""
res = sw.query(q)
print(f"Join query SUCCESS! Rows: {len(res)}")
for r in res:
    print(" ", r)
