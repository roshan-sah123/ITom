# Inventory locations

Open **Digital Workspace → Managed endpoint inventory**.

- **Location** appears next to the device name.
- Choose a site in **Location (All)** to filter the inventory. **Unassigned**
  shows devices without a reporting location.
- Location works together with search and compliance filters. Changing a filter
  returns to page one. **Reset** clears all filters.
- **Export Filtered Results (CSV)** includes every matching device across all
  pages, with Location and Location Assignment columns.

## Reading the location

| Display | Meaning |
| --- | --- |
| Site name | The device has an existing mapped reporting location. |
| Site name + Needs review | The location is provisional or needs review. |
| Unassigned | No canonical reporting location is available. |

A reporting location does not establish the device's current physical position.
Research estimates remain provisional until reviewed. Existing mapped records
may use inherited approvals; their location is not a GPS measurement.

To correct an estimate, open **Operations Analytics → Locations →
Digital Workspace · Intune → Review mappings**, find the prefix or device name,
choose the reporting location, and save the decision.

If the location list cannot load, the device inventory remains available.
Choose **Retry locations** to reload the filter options.

## Technical reference

`GET /api/v1/intune/devices?location_id=LOCATION_ID` filters canonical membership
before counting and pagination. `location_id=unassigned` selects missing canonical
membership. Each Intune list item includes `canonical_location`, `location_id`,
and `location_resolution`; raw `location` keeps its existing meaning.

Tests: `tests/test_intune_inventory_locations.py` and
`tests/browser/test_endpoint_inventory_locations.py`.

See [location research](INTUNE_LOCATION_INFERENCE.md) for inference rules and
[workspace guide](WORKSPACE_GUIDE.md) for startup, tests and local backups.
