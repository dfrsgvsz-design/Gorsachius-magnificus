# Terrestrial Vertebrate Export Parity Checklist

This checklist is the release gate for `mainland_china` and `taiwan` terrestrial vertebrate exports. It is intentionally short and should be used together with `backend/data/vertebrate_export_profiles.json`.

## Scope Freeze

- Only these protocols are in scope:
  - `bird_line_transect`
  - `bird_point_count`
  - `mammal_trap_net`
  - `herp_infrared_camera`
- Every export bundle must include exactly these outputs:
  - `event_summary`
  - `species_list`
  - `effort_summary`
  - `station_or_route_summary`
- `Plants` and `Insects` are not blockers for this release gate.

## Payload Alignment

- Event payload keys match the sprint-approved schema exactly.
- Record payload keys match the sprint-approved schema exactly.
- No export mapping depends on legacy loose `extra` blobs when a formal payload key exists.
- `mammal_trap_net` uses `welfare_notes`, not legacy alternate names.
- `herp_infrared_camera` uses `camera_station_id`, `camera_action`, `camera_days`, and `file_count` exactly as frozen.

## Jurisdiction Export Mapping

- `mainland_china` has explicit column mappings for all 4 outputs of all 4 protocols.
- `taiwan` has explicit column mappings for all 4 outputs of all 4 protocols.
- Mainland mappings prefer `zh_cn` names and mainland status flags.
- Taiwan mappings prefer `zh_tw` names and Taiwan status flags.
- Column naming differences are handled in export labels and bundle descriptors, not in storage schema forks.

## Masking and Sensitive Species

- Export mappings include coordinate masking fields for every `species_list`.
- Masking trigger inputs are available from taxonomy status flags and record-level coordinate policy.
- Export output includes:
  - coordinate masked flag
  - masking reason
  - display latitude
  - display longitude
- Canonical stored geometry remains unmasked in backend storage.

## Verification

- JSON profile file parses successfully.
- Both jurisdictions expose 4 protocols.
- Each protocol exposes exactly 4 required bundle outputs.
- Each bundle output contains explicit column mappings.
- Each `species_list` includes masking-relevant fields.
- Each `event_summary` and `effort_summary` reflects the approved event payload keys.
- Each `species_list` and `station_or_route_summary` reflects the approved record payload keys where applicable.

## Release Ready

- Export engine can consume the machine-readable profile without hand-written special cases for the 4 in-scope protocols.
- Field UI review/export surfaces can point to these same bundle definitions.
- Backend tests cover both jurisdictions and all 4 protocols.
- Final exported bundle examples are reviewed for one mainland and one Taiwan scenario before calling parity complete.
