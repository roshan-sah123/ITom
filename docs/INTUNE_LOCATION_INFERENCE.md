# Intune location inference

Intune locations are reporting assignments derived from inventory evidence.
They do not establish a device's current physical position.

Ordinary Intune mapping keys match the longest device-name prefix. An additive
`NAME:<complete device name>` key matches exactly, ignoring case and surrounding
whitespace. Exact keys take precedence over prefixes. Pending and rejected exact
decisions also take precedence, so rejecting a device exception cannot silently
restore a broader approved assignment. SolarWinds matching is unchanged.

Research estimates must retain `approval_status=PENDING`; their devices have
`location_resolution=review`. The existing Locations → Digital Workspace ·
Intune → Review mappings workflow can approve, change or reject them. Search
for a prefix or the complete device name to find its rule. Exact rules continue
to apply when the same name returns in a later sync. A rename requires fresh
research or a reviewed rule change.

## Research performed on 22 October 2026

The user requested best-effort location estimates and accepted later correction.
The local configured CMDB was examined without fetching or modifying Intune.
Existing mapped assignments were preserved. New proposals use:

- A usable serial number with exactly one mapped reporting location in retained
  inventory, excluding placeholder serials and serials with more than five rows.
  This establishes historical association; the device may have moved.
- A single mapped location among the primary user's other active devices, with
  at most three mapped peers. Obvious shared/service usernames are excluded.
  This is weaker evidence because a user's devices can be at different sites.
- Recognizable naming-family variants and explicitly provisional prefix
  hypotheses. Public company office information confirms the places exist;
  it does not independently establish the internal prefix definitions.

Exact-name proposals are generated only when every active record with that name
has a consistent candidate and none already has a location. This prevents a
duplicate name from silently changing an existing mapped assignment. Conflicting
serial references are not resolved through user association. Research proposals
are never used as evidence for additional inferred proposals in the same run.

`LP-AZ-` spans multiple mapped locations, including international associations.
It must not be assigned wholesale to one city or country. Individual researched
exceptions are possible. `CTK` has same-serial and related-device evidence for
Chennai. Low-confidence interpretations such as `CN` → Canada and `BK` → Bangkok
are hypotheses recorded in each rule's review note, with conflicting evidence
and alternatives; they require review before being treated as approved.

Public references:

- [Coforge office directory](https://www.coforge.com/who-we-are/global-presence)
- [Coforge Canadian office announcement](https://www.linkedin.com/posts/coforge-tech_officeexpansion-newoffice-growth-activity-7190797395771740160-1Y2B)
- [Encora DMI acquisition expansion announcement](https://www.linkedin.com/posts/encorainc_encora-globalexpansion-strategicgrowth-activity-7295094423271415808-Tqns)
- [Microsoft managedDevice fields](https://learn.microsoft.com/en-us/graph/api/resources/intune-devices-manageddevice?view=graph-rest-1.0)

Private local research artifacts, proposed rules, before-state records, and the
preview/apply operator script are under `outputs/intune-location-rd-2026-10-22/`.
That directory is ignored by Git and is not a static portal directory. Individual
proposals have append-only audit records in `location_mapping_reviews`. The
operator script checks inventory identities and operational fields, existing
mapped Intune assignments, and SolarWinds assignments before committing. It
previews in a transaction and rolls back by default. The source's successful-sync
timestamp is not advanced by mapping research.
