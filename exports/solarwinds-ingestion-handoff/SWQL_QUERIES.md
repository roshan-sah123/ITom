# Active SolarWinds SWQL Queries

Authority: `source/src/sync/solarwinds_client.py`, `_fetch_complete_pages` and
the three `fetch_*` methods. These are the complete query families invoked by
`SolarWindsSource.fetch` for the live database ingestion path.

All are GET requests with the SWQL text in the `query` URL parameter. A count
query runs both before and after the pages for its entity. Page bounds are
one-based, inclusive, and at most 500 rows. Replace `<start>` and `<end>` below
with computed bounds; the placeholders are documentation, not valid SWQL.

## Nodes and Custom Properties

```sql
SELECT COUNT(*) AS Total
FROM Orion.Nodes n
LEFT JOIN Orion.NodesCustomProperties cp ON n.NodeID = cp.NodeID
```

```sql
SELECT n.NodeID,
       n.Caption,
       n.IPAddress,
       n.Status,
       n.StatusDescription,
       n.CPULoad,
       n.PercentMemoryUsed,
       n.ResponseTime,
       n.AvgResponseTime,
       n.Vendor,
       n.MachineType,
       n.LastSync,
       n.SystemUpTime,
       n.NodeDescription,
       cp.City AS City,
       cp.ITSM_Location AS ITSM_Location,
       cp.NodeCategory AS NodeCategory,
       cp.NodeType AS NodeType,
       n.Contact
FROM Orion.Nodes n
LEFT JOIN Orion.NodesCustomProperties cp ON n.NodeID = cp.NodeID
ORDER BY n.NodeID
WITH ROWS <start> TO <end>
```

The four named custom properties must exist in the target Orion schema. There
is no MachineType/server-only WHERE filter: this fetch includes all nodes.

## Native Groups

```sql
SELECT COUNT(*) AS Total FROM Orion.Container
```

```sql
SELECT ContainerID, Name, Owner, IsDeleted, Status, StatusDescription
FROM Orion.Container
ORDER BY ContainerID
WITH ROWS <start> TO <end>
```

Core-owner and deletion filtering happens in Python after fetching, not in SWQL.

## Native Group Memberships

```sql
SELECT COUNT(*) AS Total FROM Orion.ContainerMembers
```

```sql
SELECT ContainerID, MemberPrimaryID, MemberEntityType
FROM Orion.ContainerMembers
ORDER BY ContainerID, MemberEntityType, MemberPrimaryID
WITH ROWS <start> TO <end>
```

Keys are checked in this exact order even though the SELECT column order is
different. The Python validator resolves retained edges to groups and nodes.

## Database Queries and Writes

CMDB queries and writes use SQLAlchemy rather than SWQL. See
`source/app/services/sync_service.py` for node lookup/update/history/retirement,
`source/app/repositories/solarwinds_group_repository.py` for group replacement,
and `source/app/services/location_service.py` for mapping and observation writes.
The PostgreSQL locking statement is `SELECT pg_try_advisory_xact_lock(:key)`.