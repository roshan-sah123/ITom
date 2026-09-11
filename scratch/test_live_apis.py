import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

# 1. Test SolarWinds SWIS connectivity
print("--- TESTING SOLARWINDS SWIS API ---")
host = os.getenv("SOLARWINDS_HOST")
port = os.getenv("SOLARWINDS_PORT", "17774")
user = os.getenv("SOLARWINDS_USERNAME")
pwd = os.getenv("SOLARWINDS_PASSWORD")

print(f"Host: {host}:{port}, User: {user}")
if host and user and pwd:
    try:
        from src.sync.solarwinds_client import SolarWindsClient
        sw = SolarWindsClient(host=host, port=int(port), username=user, password=pwd, timeout=15)
        # Test query TOP 5 nodes
        res = sw.query("SELECT TOP 5 NodeID, Caption, Status, CPULoad, PercentMemoryUsed, CustomProperties.City AS City FROM Orion.Nodes")
        print(f"SolarWinds live query SUCCESS! Rows returned: {len(res)}")
        for r in res:
            print("  Node:", r.get("NodeID"), r.get("Caption"), "| Status:", r.get("Status"), "| City:", r.get("City"))
    except Exception as e:
        print("SolarWinds error:", e)
else:
    print("SolarWinds credentials missing in .env")

# 2. Test Microsoft Graph Intune connectivity
print("\n--- TESTING MICROSOFT GRAPH INTUNE API ---")
tenant_id = os.getenv("AZURE_TENANT_ID")
client_id = os.getenv("AZURE_CLIENT_ID")
client_sec = os.getenv("AZURE_CLIENT_SECRET")
print(f"Tenant: {tenant_id}, Client: {client_id}")

if tenant_id and client_id and client_sec:
    try:
        from src.sync.graph_client import GraphClient
        gc = GraphClient(tenant_id=tenant_id, client_id=client_id, client_secret=client_sec, timeout=15)
        # Test fetching managed devices top 5
        devices = gc.fetch_managed_devices(max_devices=5)
        print(f"Intune Graph API live fetch SUCCESS! Devices returned: {len(devices)}")
        for d in devices:
            print("  Device:", d.get("id"), d.get("deviceName"), "| OS:", d.get("operatingSystem"), "| Compliance:", d.get("complianceState"))
    except Exception as e:
        print("Intune Graph API error:", e)
else:
    print("Intune credentials missing in .env")
